use std::io::Write;
use std::path::Path;
use std::process::{Command, Stdio};

use anyhow::{Context, Result, bail};

use crate::util::ssebench_repo_path;

use super::diff::{commit_count, get_full_diff, root_commit, run_git};

/// Prepare the grading environment.
///
/// This operation:
///   1. Captures the agent's full diff and commit messages.
///   2. Saves them to the archive directory (`final.patch`, `commits.log`).
///   3. Applies the agent's diff to `$SSE_REPO_PATH` — a pre-populated clean
///      clone of the original repo that retains vendor code, downloaded caches,
///      and other gitignored-but-necessary files.
///
/// The live source folder is **not** modified, so no build artifacts or cached
/// dependencies are destroyed.  Tests and builds during grading must use
/// `$SSE_REPO_PATH` as their source root (see `Bencher` with `grading = true`).
pub fn prepare_grading(source_folder: &Path, archive_dir: &Path) -> Result<()> {
    // 1. Capture the agent's diff
    let diff = get_full_diff(source_folder).context("failed to capture agent diff")?;

    // 2. Capture commit messages (only if the agent made commits)
    let commits = if commit_count(source_folder)? > 1 {
        let root = root_commit(source_folder)?;
        let range = format!("{}..HEAD", root);
        run_git(
            source_folder,
            &["log", "--format=%H%n%s%n%b%n---", &range],
            false,
        )
        .unwrap_or_default()
    } else {
        String::new()
    };

    // 3. Save to archive
    std::fs::create_dir_all(archive_dir)
        .with_context(|| format!("failed to create archive dir: {}", archive_dir.display()))?;
    std::fs::write(archive_dir.join("final.patch"), &diff)
        .context("failed to write final.patch")?;
    std::fs::write(archive_dir.join("commits.log"), &commits)
        .context("failed to write commits.log")?;

    // 4. Apply the agent's diff to $SSE_REPO_PATH (only if non-empty)
    let repo = ssebench_repo_path();
    if !diff.trim().is_empty() {
        apply_patch(&repo, &diff).context("failed to apply agent patch to repo")?;
    }

    Ok(())
}

/// Pipe a patch into `git apply --binary` via stdin.
fn apply_patch(cwd: &Path, patch: &str) -> Result<()> {
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
        .write_all(patch.as_bytes())
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
