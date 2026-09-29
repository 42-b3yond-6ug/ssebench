use std::path::Path;
use std::process::Command;

use anyhow::{Result, anyhow};

/// Collect a full unified diff of all changes since the origin buggy commit.
///
/// **Strategy:**
/// - If there is more than one commit, the agent has already committed their
///   fix.  We return `git diff <root>..HEAD` which cleanly shows everything
///   the agent changed on top of the original buggy commit.
/// - If there is exactly one commit (the buggy commit itself), the agent is
///   still working.  We fall back to the non-intrusive working-tree approach:
///     1. Staged (index) vs HEAD
///     2. Unstaged (working tree) vs index
///
/// Both paths produce a single concatenated diff string with binary support
/// and zero repo mutation.
pub fn get_full_diff(source_folder: &Path) -> Result<String> {
    let count = commit_count(source_folder)?;

    if count > 1 {
        return get_committed_diff(source_folder);
    }

    get_working_tree_diff(source_folder)
}

/// Diff between the root (origin buggy) commit and HEAD.
///
/// Used when the agent has already committed their changes.
fn get_committed_diff(source_folder: &Path) -> Result<String> {
    let root = root_commit(source_folder)?;
    let range = format!("{}..HEAD", root);

    run_git(
        source_folder,
        &["diff", "--binary", "--no-color", "--patch", &range],
        false,
    )
}

/// Collect uncommitted changes from the working tree (staged + unstaged).
///
/// Used when the agent is still actively editing and has not yet committed.
fn get_working_tree_diff(source_folder: &Path) -> Result<String> {
    let mut sections: Vec<String> = Vec::new();

    // 1. Staged (index) vs HEAD
    let staged = run_git(
        source_folder,
        &[
            "diff",
            "--cached",
            "--binary",
            "--no-color",
            "--patch",
            "HEAD",
        ],
        false,
    )?;
    if !staged.is_empty() {
        sections.push(staged);
    }

    // 2. Unstaged (working tree) vs index
    let unstaged = run_git(
        source_folder,
        &["diff", "--binary", "--no-color", "--patch"],
        false,
    )?;
    if !unstaged.is_empty() {
        sections.push(unstaged);
    }

    Ok(sections.join("\n"))
}

/// Return the number of commits reachable from HEAD.
pub(super) fn commit_count(cwd: &Path) -> Result<u64> {
    let output = run_git(cwd, &["rev-list", "--count", "HEAD"], false)?;
    output
        .trim()
        .parse::<u64>()
        .map_err(|e| anyhow!("failed to parse commit count: {}", e))
}

/// Return the hash of the root (first / origin buggy) commit.
pub(super) fn root_commit(cwd: &Path) -> Result<String> {
    let output = run_git(cwd, &["rev-list", "--max-parents=0", "HEAD"], false)?;
    output
        .lines()
        .next()
        .map(|s| s.trim().to_string())
        .ok_or_else(|| anyhow!("no root commit found"))
}

/// Run a git command in the given directory and return its stdout as a String.
///
/// When `allow_exit_one` is true, exit code 1 is treated as success (needed for
/// `git diff --no-index` which returns 1 when differences are found).
pub(super) fn run_git(cwd: &Path, args: &[&str], allow_exit_one: bool) -> Result<String> {
    let output = Command::new("git")
        .args(args)
        .current_dir(cwd)
        .output()
        .map_err(|e| anyhow!("failed to execute git {}: {}", args.join(" "), e))?;

    let code = output.status.code().unwrap_or(-1);
    let ok = output.status.success() || (allow_exit_one && code == 1);

    if !ok {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(anyhow!(
            "git {} failed (exit {}): {}",
            args.join(" "),
            code,
            stderr,
        ));
    }

    Ok(String::from_utf8_lossy(&output.stdout).into_owned())
}
