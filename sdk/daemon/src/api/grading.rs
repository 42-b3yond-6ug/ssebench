use std::io::Write;
use std::path::Path;
use std::process::{Command, Stdio};

use anyhow::{Context, Result, bail};

use crate::util::ssebench_repo_path;

use super::diff::Baseline;

/// Prepare the grading environment.
///
/// This operation:
///   1. Captures the agent's changes against the task's base commit (see
///      [`Baseline::diff`]) and the messages of its commits.
///   2. Saves them to the archive directory (`final.patch`, `commits.log`).
///   3. Applies the agent's diff to `$SSE_REPO_PATH` — a pre-populated clean
///      clone of the original repo that retains vendor code, downloaded caches,
///      and other gitignored-but-necessary files.
///
/// The live source folder is **not** modified, so no build artifacts or cached
/// dependencies are destroyed.  Tests and builds during grading must use
/// `$SSE_REPO_PATH` as their source root (see `Bencher` with `grading = true`).
pub fn prepare_grading(baseline: &Baseline, archive_dir: &Path) -> Result<()> {
    // 1. Capture the agent's diff and commit messages
    let diff = baseline.diff().context("failed to capture agent diff")?;
    let commits = baseline.commit_messages();

    // 2. Save to archive
    std::fs::create_dir_all(archive_dir)
        .with_context(|| format!("failed to create archive dir: {}", archive_dir.display()))?;
    std::fs::write(archive_dir.join("final.patch"), &diff)
        .context("failed to write final.patch")?;
    std::fs::write(archive_dir.join("commits.log"), &commits)
        .context("failed to write commits.log")?;

    // 3. Apply the agent's diff to $SSE_REPO_PATH (only if non-empty)
    let repo = ssebench_repo_path();
    if !diff.trim_ascii().is_empty() {
        apply_patch(&repo, &diff).context("failed to apply agent patch to repo")?;
    }

    Ok(())
}

/// Pipe a patch into `git apply --binary` via stdin.
fn apply_patch(cwd: &Path, patch: &[u8]) -> Result<()> {
    let mut child = Command::new("git")
        .args(["apply", "--binary"])
        .current_dir(cwd)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .context("failed to spawn git apply")?;

    child
        .stdin
        .take()
        .expect("stdin was piped")
        .write_all(patch)
        .context("failed to write patch to git apply stdin")?;

    let output = child
        .wait_with_output()
        .context("failed to wait for git apply")?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        bail!("git apply failed: {}", stderr);
    }

    Ok(())
}
