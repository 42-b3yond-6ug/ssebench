use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::Arc;

use anyhow::{Result, anyhow, bail};
use serde::Deserialize;
use tempfile::TempDir;

use crate::bench::BenchCore;
use crate::util::{copy_folder_to_temp, create_timestamped_log, run_script, ssebench_repo_path};

use super::Tool;
use super::response::{ScriptResult, ToolResult};
use super::{ToolRequest, ToolResponse, parse_and_run};

/// Tool-specific result alias
pub type BencherResult = ScriptResult;

/// Bencher tool for build/test/poc operations.
#[derive(Debug)]
pub struct Bencher {
    bench: Arc<BenchCore>,
    latest_build_folder: Option<Box<TempDir>>,
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
                    .ok_or_else(|| anyhow!("intent_test not configured"))?;

                self.run_tests_with_patch(patch, arg.grading)
                    .map(ToolResult::Script)
                    .map_err(|e| anyhow!("{}", e))
            }),

            _ => bail!("invalid action: {}", request.action),
        }
    }
}

impl Bencher {
    pub fn new(bench: Arc<BenchCore>) -> Self {
        Self {
            bench,
            latest_build_folder: None,
        }
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
            .as_deref()
            .ok_or_else(|| anyhow!("build script not configured"))?;
        let source = self.effective_source(grading);
        let temp_dir = copy_folder_to_temp(&source)?;
        let result = run_script(script.to_str().unwrap(), &[], temp_dir.path()).map(Into::into);
        self.latest_build_folder = Some(Box::new(temp_dir));
        result
    }

    /// Run the specific PoC.
    ///
    /// Always uses the folder produced by the last `build` call, regardless of
    /// the `grading` flag (the build already copied the right source).
    pub fn run_poc(&mut self, poc: &str) -> Result<BencherResult> {
        let script = self
            .bench
            .scripts()
            .run
            .as_deref()
            .ok_or_else(|| anyhow!("run script not configured"))?;
        match &self.latest_build_folder {
            Some(cwd) => {
                run_script(script.to_str().unwrap(), &[poc.into()], cwd.path()).map(Into::into)
            }
            None => Ok(BencherResult::new(
                -1,
                String::new(),
                "project hasn't been built yet - call 'build' action first".into(),
            )),
        }
    }

    /// Run the function test suite.
    ///
    /// When `grading` is `true`, the tests are run against `$SSE_REPO_PATH`.
    pub fn run_tests(&self, grading: bool) -> Result<BencherResult> {
        let script = self
            .bench
            .scripts()
            .test
            .as_deref()
            .ok_or_else(|| anyhow!("test script not configured"))?;
        let source = self.effective_source(grading);
        let temp_dir = copy_folder_to_temp(&source)?;
        run_script(script.to_str().unwrap(), &[], temp_dir.path()).map(Into::into)
    }

    /// Run test with a patch. The patch can be used to add new tests, or modify existing tests.
    ///
    /// When `grading` is `true`, the tests are run against `$SSE_REPO_PATH`.
    pub fn run_tests_with_patch(&self, test_patch: &Path, grading: bool) -> Result<BencherResult> {
        let script = self
            .bench
            .scripts()
            .test
            .as_deref()
            .ok_or_else(|| anyhow!("test script not configured"))?;
        let source = self.effective_source(grading);
        let temp_dir = copy_folder_to_temp(&source)?;

        let patch_output = Command::new("git")
            .current_dir(temp_dir.path())
            .arg("apply")
            .arg("-p1")
            .arg(test_patch)
            .output()?;

        let stdout = String::from_utf8_lossy(&patch_output.stdout);
        let stderr = String::from_utf8_lossy(&patch_output.stderr);

        if let Ok(mut f) = create_timestamped_log("patch") {
            writeln!(f, "git apply -p1 {:?}", test_patch).ok();
            writeln!(f, "code={}", patch_output.status).ok();
            writeln!(f, "=== stdout ===\n{:?}", stdout).ok();
            writeln!(f, "=== stderr ===\n{:?}", stderr).ok();
        }

        if !patch_output.status.success() {
            bail!("git apply failed, {}, {}", stdout, stderr);
        }

        run_script(script.to_str().unwrap(), &[], temp_dir.path()).map(Into::into)
    }
}
