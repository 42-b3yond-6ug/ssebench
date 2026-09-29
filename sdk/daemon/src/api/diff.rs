//! Capture of the agent's changes to the source tree.
//!
//! The agent owns the source tree and its `.git`: it may commit, amend,
//! rewrite history, change the repository's configuration or delete it. The
//! capture depends on none of that. At startup, before the agent runs,
//! [`record_baseline`] copies the tree's single commit into a private
//! repository. A capture then diffs the working tree against that commit with
//! its own index and an empty configuration, so it takes every change: staged
//! or not, committed or not, and new files that are not ignored.
//!
//! When the daemon runs as root, git runs as the owner of the source tree, the
//! agent's user: whatever the agent put in the tree is read with the agent's
//! own permissions, never with the daemon's.

use std::ffi::OsStr;
use std::io::Write;
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{Mutex, OnceLock};

use anyhow::{Context, Result, anyhow, bail};
use serde::Serialize;
use tempfile::TempDir;

static BASELINE: OnceLock<std::result::Result<Baseline, String>> = OnceLock::new();

/// Record the baseline of the source tree. Call it once, at startup, before
/// the agent can change the tree.
pub fn record_baseline(source_folder: &Path) {
    let baseline = Baseline::record(source_folder).map_err(|e| format!("{e:#}"));
    match &baseline {
        Ok(b) => log::info!(
            "Recorded the baseline of {}: {}",
            source_folder.display(),
            b.base()
        ),
        Err(e) => log::error!("No baseline of {}: {}", source_folder.display(), e),
    }
    if BASELINE.set(baseline).is_err() {
        log::warn!("The baseline was already recorded");
    }
}

/// The baseline recorded at startup.
pub fn baseline() -> Result<&'static Baseline> {
    match BASELINE.get() {
        Some(Ok(baseline)) => Ok(baseline),
        Some(Err(e)) => Err(anyhow!("no baseline of the source tree: {e}")),
        None => Err(anyhow!("the baseline of the source tree was not recorded")),
    }
}

/// One file the agent changed, for `GET /files`.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ChangedFile {
    pub path: String,
    /// `added`, `deleted` or `modified`.
    pub status: String,
    /// Lines added; 0 for a binary file.
    pub additions: u32,
    /// Lines deleted; 0 for a binary file.
    pub deletions: u32,
}

/// The source tree's initial commit, kept in a private repository.
pub struct Baseline {
    /// Holds `repo.git`, the capture's `index`, and serves as git's HOME.
    dir: TempDir,
    worktree: PathBuf,
    base: String,
    /// User and group to run git as, when the daemon runs as root and the
    /// tree belongs to another user.
    user: Option<(u32, u32)>,
    /// Captures share one index.
    lock: Mutex<()>,
}

impl Baseline {
    /// Copy the commit at `HEAD` of the repository in `worktree`, with its
    /// objects, into a new private repository.
    pub fn record(worktree: &Path) -> Result<Self> {
        let dir = tempfile::Builder::new()
            .prefix("ssebench-baseline-")
            .tempdir()
            .context("failed to create the baseline directory")?;
        let tree = std::fs::metadata(worktree)
            .with_context(|| format!("source tree {}", worktree.display()))?;
        // The directory was just created, so it belongs to the daemon's user.
        let daemon_uid = std::fs::metadata(dir.path())?.uid();
        let user = (daemon_uid == 0 && tree.uid() != 0).then(|| (tree.uid(), tree.gid()));
        if let Some((uid, gid)) = user {
            std::os::unix::fs::chown(dir.path(), Some(uid), Some(gid))
                .context("failed to hand the baseline directory to the tree's owner")?;
        }

        let mut baseline = Baseline {
            dir,
            worktree: worktree.to_path_buf(),
            base: String::new(),
            user,
            lock: Mutex::new(()),
        };
        let mut clone = baseline.command(None);
        clone
            .args([
                "clone",
                "--quiet",
                "--bare",
                "--local",
                "--no-hardlinks",
                "--",
            ])
            .arg(worktree)
            .arg(baseline.repo());
        run(clone, None).context("failed to copy the source tree's repository")?;
        let head = baseline.git(&["rev-parse", "--verify", "HEAD^{commit}"])?;
        baseline.base = String::from_utf8_lossy(&head).trim().to_string();
        Ok(baseline)
    }

    /// The commit the capture diffs against.
    pub fn base(&self) -> &str {
        &self.base
    }

    /// The agent's changes: a patch from the base commit to the working tree,
    /// with binary changes and new files that are not ignored.
    pub fn diff(&self) -> Result<Vec<u8>> {
        let _guard = self.lock.lock().unwrap_or_else(|e| e.into_inner());
        self.stage_working_tree()?;
        self.git(&[
            "diff",
            "--binary",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            &self.base,
        ])
    }

    /// The files [`Baseline::diff`] changes, with their line counts.
    pub fn changed_files(&self) -> Result<Vec<ChangedFile>> {
        let _guard = self.lock.lock().unwrap_or_else(|e| e.into_inner());
        self.stage_working_tree()?;
        let status = self.git(&["diff", "--name-status", "-z", "--no-renames", &self.base])?;
        let numstat = self.git(&["diff", "--numstat", "-z", "--no-renames", &self.base])?;

        let counts: std::collections::HashMap<String, (u32, u32)> = split_nul(&numstat)
            .filter_map(|record| {
                let mut fields = record.splitn(3, |&b| b == b'\t');
                let additions = parse_count(fields.next()?);
                let deletions = parse_count(fields.next()?);
                Some((lossy(fields.next()?), (additions, deletions)))
            })
            .collect();

        let fields: Vec<&[u8]> = split_nul(&status).collect();
        Ok(fields
            .as_chunks::<2>()
            .0
            .iter()
            .map(|[status, path]| {
                let path = lossy(path);
                let status = match status.first() {
                    Some(b'A') => "added",
                    Some(b'D') => "deleted",
                    _ => "modified",
                };
                let (additions, deletions) = counts.get(&path).copied().unwrap_or((0, 0));
                ChangedFile {
                    path,
                    status: status.to_string(),
                    additions,
                    deletions,
                }
            })
            .collect())
    }

    /// Hash, subject and body of each commit the agent made on top of the
    /// base, from the agent's own repository; empty when it made none or its
    /// repository no longer has them.
    pub fn commit_messages(&self) -> String {
        let mut cmd = self.command(Some(&self.worktree.join(".git")));
        cmd.args(["log", "--format=%H%n%s%n%b%n---"])
            .arg(format!("{}..HEAD", self.base));
        match run(cmd, None) {
            Ok(out) => String::from_utf8_lossy(&out).into_owned(),
            Err(e) => {
                log::warn!("No commit messages: {e:#}");
                String::new()
            }
        }
    }

    fn repo(&self) -> PathBuf {
        self.dir.path().join("repo.git")
    }

    /// Reset the private index to the base commit and add the untracked files
    /// that are not ignored, without their content, so that `git diff <base>`
    /// covers them. No object is written.
    fn stage_working_tree(&self) -> Result<()> {
        // --reset keeps the cached stat data of unchanged files, so only the
        // files that changed are read again.
        self.git(&["read-tree", "--reset", &self.base])?;
        let untracked = self.git(&["ls-files", "-z", "--others", "--exclude-standard"])?;
        // A nested repository is listed as a directory: leave it out rather
        // than record another repository's commit.
        let paths: Vec<&[u8]> = split_nul(&untracked)
            .filter(|p| !p.ends_with(b"/"))
            .collect();
        if !paths.is_empty() {
            let mut add = self.command(Some(&self.repo()));
            add.args([
                "add",
                "--intent-to-add",
                "--pathspec-from-file=-",
                "--pathspec-file-nul",
            ]);
            run(add, Some(&paths.join(&0u8))).context("failed to list the new files")?;
        }
        Ok(())
    }

    fn git(&self, args: &[&str]) -> Result<Vec<u8>> {
        let mut cmd = self.command(Some(&self.repo()));
        cmd.args(args);
        run(cmd, None)
    }

    /// A git command on `git_dir` (none for `clone`), with the working tree,
    /// the private index, no system or user configuration, and paths taken
    /// literally.
    fn command(&self, git_dir: Option<&Path>) -> Command {
        let mut cmd = Command::new("git");
        cmd.env_clear()
            .env("PATH", std::env::var_os("PATH").unwrap_or_default())
            .env("HOME", self.dir.path())
            .env("XDG_CONFIG_HOME", self.dir.path())
            .env("GIT_CONFIG_NOSYSTEM", "1")
            .env("GIT_CONFIG_GLOBAL", "/dev/null")
            .env("GIT_LITERAL_PATHSPECS", "1")
            .env("GIT_TERMINAL_PROMPT", "0")
            .env("LC_ALL", "C")
            .current_dir(&self.worktree);
        if let Some(git_dir) = git_dir {
            cmd.env("GIT_DIR", git_dir)
                .env("GIT_WORK_TREE", &self.worktree)
                .env("GIT_INDEX_FILE", self.dir.path().join("index"));
        }
        if let Some((uid, gid)) = self.user {
            use std::os::unix::process::CommandExt;
            cmd.uid(uid).gid(gid);
        }
        cmd
    }
}

/// Run a command, feeding it `stdin`, and return its standard output.
fn run(mut cmd: Command, stdin: Option<&[u8]>) -> Result<Vec<u8>> {
    let args: Vec<String> = cmd
        .get_args()
        .map(OsStr::to_string_lossy)
        .map(|a| a.into_owned())
        .collect();
    let mut child = cmd
        .stdin(if stdin.is_some() {
            Stdio::piped()
        } else {
            Stdio::null()
        })
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .with_context(|| format!("failed to run git {}", args.join(" ")))?;
    if let Some(input) = stdin {
        child
            .stdin
            .take()
            .expect("stdin is piped")
            .write_all(input)
            .with_context(|| format!("failed to write to git {}", args.join(" ")))?;
    }
    let output = child.wait_with_output()?;
    if !output.status.success() {
        bail!(
            "git {} failed ({}): {}",
            args.join(" "),
            output.status,
            String::from_utf8_lossy(&output.stderr).trim()
        );
    }
    Ok(output.stdout)
}

fn split_nul(bytes: &[u8]) -> impl Iterator<Item = &[u8]> {
    bytes.split(|&b| b == 0).filter(|s| !s.is_empty())
}

fn lossy(bytes: &[u8]) -> String {
    String::from_utf8_lossy(bytes).into_owned()
}

/// A numstat count; `-` for a binary file counts as 0.
fn parse_count(field: &[u8]) -> u32 {
    std::str::from_utf8(field)
        .ok()
        .and_then(|s| s.parse().ok())
        .unwrap_or(0)
}

#[cfg(test)]
mod tests;
