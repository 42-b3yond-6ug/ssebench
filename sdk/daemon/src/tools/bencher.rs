use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::sync::Arc;

use anyhow::{Result, anyhow, bail};
use serde::Deserialize;

use crate::bench::BenchCore;
use crate::isolation::{TaskRunner, Workspace, remove_tree};
use crate::util::{create_timestamped_log, ssebench_repo_path};

use super::Tool;
use super::response::{ScriptResult, ToolResult};
use super::{ToolRequest, ToolResponse, parse_and_run};

/// Tool-specific result alias
pub type BencherResult = ScriptResult;

/// Bencher tool for build/test/poc operations.
///
/// Every script runs through the [`TaskRunner`]: as the unprivileged runner,
/// in a workspace that holds a copy of the project and only the hidden
/// material that the check needs, staged by root just before it runs.
pub struct Bencher {
    bench: Arc<BenchCore>,
    runner: TaskRunner,
    latest_build: Option<Workspace>,
}

impl std::fmt::Debug for Bencher {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Bencher")
            .field("latest_build", &self.latest_build)
            .finish_non_exhaustive()
    }
}

/// Arguments for actions that only carry the grading flag.
#[derive(Debug, Deserialize, Default)]
struct GradingArg {
    #[serde(default)]
    grading: bool,
}

#[derive(Debug, Deserialize)]
struct RunArgument {
    poc: String,
}

impl Tool for Bencher {
    fn name(&self) -> String {
        "bencher".into()
    }

    fn description(&self) -> String {
        "Build, test, and run PoC operations".into()
    }

    fn handle(&mut self, request: ToolRequest) -> ToolResponse {
        match request.action.as_str() {
            "build" => parse_and_run::<GradingArg, _>(&request, |arg| {
                self.build(arg.grading)
                    .map(ToolResult::Script)
                    .map_err(|e| anyhow!("{}", e))
            }),

            "run_poc" => parse_and_run::<RunArgument, _>(&request, |argument| {
                self.run_poc(&argument.poc)
                    .map(ToolResult::Script)
                    .map_err(|e| anyhow!("{}", e))
            }),

            "function_test" => parse_and_run::<GradingArg, _>(&request, |arg| {
                self.run_tests(arg.grading)
                    .map(ToolResult::Script)
                    .map_err(|e| anyhow!("{}", e))
            }),

            "intent_test" => parse_and_run::<GradingArg, _>(&request, |arg| {
                let patch = self
                    .bench
                    .intent_test_patch()
                    .ok_or_else(|| anyhow!("intent_test not configured"))?
                    .to_path_buf();

                self.run_tests_with_patch(&patch, arg.grading)
                    .map(ToolResult::Script)
                    .map_err(|e| anyhow!("{}", e))
            }),

            _ => bail!("invalid action: {}", request.action),
        }
    }
}

impl Bencher {
    pub fn new(bench: Arc<BenchCore>, runner: TaskRunner) -> Self {
        Self {
            bench,
            runner,
            latest_build: None,
        }
    }

    /// Start grading with a new runner session: nothing a check left behind
    /// during the agent phase (a process, a cache, a changed support
    /// directory, a build) is used by the checks that grade.
    pub fn start_grading(&mut self) -> Result<()> {
        self.latest_build = None;
        self.runner.new_session()
    }

    /// Return the source folder to use: `$SSE_REPO_PATH` when grading, otherwise
    /// the project's configured source folder.
    fn effective_source(&self, grading: bool) -> PathBuf {
        if grading {
            ssebench_repo_path()
        } else {
            self.bench.source_folder().to_path_buf()
        }
    }

    /// A workspace with a copy of the project.
    fn project_workspace(&mut self, grading: bool) -> Result<Workspace> {
        let source = self.effective_source(grading);
        let workspace = self.runner.workspace()?;
        self.runner.copy_source(&source, &workspace)?;
        Ok(workspace)
    }

    /// Build the project, keep the latest build folder.
    ///
    /// When `grading` is `true`, the build is performed against `$SSE_REPO_PATH`
    /// (a clean clone of the original repo with vendor/cache intact) rather than
    /// the live source folder.
    pub fn build(&mut self, grading: bool) -> Result<BencherResult> {
        let script = self
            .bench
            .scripts()
            .build
            .clone()
            .ok_or_else(|| anyhow!("build script not configured"))?;
        // The previous build folder goes before the new copy is made.
        self.latest_build = None;
        let workspace = self.project_workspace(grading)?;
        let mut cmd = self.runner.command(&script);
        cmd.current_dir(workspace.src());
        let result = self.runner.run(cmd).map(Into::into);
        self.latest_build = Some(workspace);
        result
    }

    /// Run the specific PoC.
    ///
    /// Always uses the folder produced by the last `build` call, regardless of
    /// the `grading` flag (the build already copied the right source). The run
    /// script and the proof of concept are root-only; they are copied into
    /// the build's workspace for this run and removed after it.
    pub fn run_poc(&mut self, poc: &str) -> Result<BencherResult> {
        let script = self
            .bench
            .scripts()
            .run
            .clone()
            .ok_or_else(|| anyhow!("run script not configured"))?;
        let poc = self
            .bench
            .find_poc(poc)
            .ok_or_else(|| anyhow!("not a PoC of this task: {poc}"))?
            .to_path_buf();
        let Some(build) = &self.latest_build else {
            return Ok(BencherResult::new(
                -1,
                String::new(),
                "project hasn't been built yet - call 'build' action first".into(),
            ));
        };

        let staged = build.path().join("poc");
        let result = self
            .stage_poc(&script, &poc, &staged)
            .and_then(|(script, poc)| {
                let mut cmd = self.runner.command(&script);
                cmd.arg(&poc).current_dir(build.src());
                self.runner.run(cmd)
            });
        remove_tree(&staged)?;
        result.map(Into::into)
    }

    /// Copy the run script and the PoC into `dir`. The PoC comes with the
    /// rest of its top-level directory (for example a Go module in `pocs/`),
    /// unless that directory also holds other hidden files.
    fn stage_poc(&self, script: &Path, poc: &Path, dir: &Path) -> Result<(PathBuf, PathBuf)> {
        let name = script
            .file_name()
            .ok_or_else(|| anyhow!("run script has no file name"))?;
        let staged_script = dir.join("script").join(name);
        self.runner.stage_file(script, &staged_script, 0o700)?;

        let relative = poc
            .strip_prefix(self.bench.root())
            .map_err(|_| anyhow!("PoC outside the task directory: {}", poc.display()))?;
        let files = dir.join("files");
        let staged_poc = files.join(relative);
        let top = match relative.components().next() {
            Some(Component::Normal(top)) if relative.components().count() > 1 => {
                Some(self.bench.root().join(top))
            }
            _ => None,
        };
        let shares_top = top.as_ref().is_some_and(|top| {
            self.bench
                .hidden_files()
                .iter()
                .all(|f| !f.starts_with(top) || self.bench.metadata().files.poc.contains(f))
        });
        match top {
            Some(top) if shares_top => {
                let dst = files.join(top.file_name().unwrap_or_default());
                self.runner.stage_dir(&top, &dst)?;
            }
            _ => self.runner.stage_file(poc, &staged_poc, 0o600)?,
        }
        Ok((staged_script, staged_poc))
    }

    /// Run the function test suite.
    ///
    /// When `grading` is `true`, the tests are run against `$SSE_REPO_PATH`.
    pub fn run_tests(&mut self, grading: bool) -> Result<BencherResult> {
        let script = self
            .bench
            .scripts()
            .test
            .clone()
            .ok_or_else(|| anyhow!("test script not configured"))?;
        let workspace = self.project_workspace(grading)?;
        let mut cmd = self.runner.command(&script);
        cmd.current_dir(workspace.src());
        self.runner.run(cmd).map(Into::into)
    }

    /// Run test with a patch. The patch can be used to add new tests, or modify existing tests.
    ///
    /// When `grading` is `true`, the tests are run against `$SSE_REPO_PATH`.
    /// The runner applies the patch itself, from a copy root puts in the
    /// workspace: git reads the copied project's configuration, which is the
    /// agent's during the agent phase.
    pub fn run_tests_with_patch(
        &mut self,
        test_patch: &Path,
        grading: bool,
    ) -> Result<BencherResult> {
        let script = self
            .bench
            .scripts()
            .test
            .clone()
            .ok_or_else(|| anyhow!("test script not configured"))?;
        let workspace = self.project_workspace(grading)?;

        let staged = workspace.path().join("tests.diff");
        self.runner.stage_file(test_patch, &staged, 0o600)?;
        let mut apply = self.runner.command("git");
        apply
            .args(["apply", "-p1"])
            .arg(&staged)
            .current_dir(workspace.src());
        let patch_output = self.runner.run(apply)?;
        std::fs::remove_file(&staged)?;

        if let Ok(mut f) = create_timestamped_log("patch") {
            writeln!(f, "git apply -p1 {:?}", test_patch).ok();
            writeln!(f, "code={}", patch_output.code).ok();
            writeln!(f, "=== stdout ===\n{:?}", patch_output.stdout).ok();
            writeln!(f, "=== stderr ===\n{:?}", patch_output.stderr).ok();
        }

        if !patch_output.success() {
            bail!(
                "git apply failed, {}, {}",
                patch_output.stdout,
                patch_output.stderr
            );
        }

        let mut cmd = self.runner.command(&script);
        cmd.current_dir(workspace.src());
        self.runner.run(cmd).map(Into::into)
    }
}
