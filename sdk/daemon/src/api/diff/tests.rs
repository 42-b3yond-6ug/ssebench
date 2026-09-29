use std::fs;
use std::os::unix::fs::{PermissionsExt, symlink};
use std::path::Path;
use std::process::Command;

use tempfile::TempDir;

use super::{Baseline, ChangedFile};

/// Run git in `dir` as a user would, with a throwaway identity.
fn git(dir: &Path, args: &[&str]) -> String {
    let out = Command::new("git")
        .args([
            "-c",
            "user.name=agent",
            "-c",
            "user.email=agent@example.org",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "init.defaultBranch=main",
        ])
        .args(args)
        .current_dir(dir)
        .env("GIT_CONFIG_GLOBAL", "/dev/null")
        .env("GIT_CONFIG_NOSYSTEM", "1")
        .output()
        .expect("git runs");
    assert!(
        out.status.success(),
        "git {args:?}: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    String::from_utf8_lossy(&out.stdout).into_owned()
}

fn write(dir: &Path, path: &str, content: impl AsRef<[u8]>) {
    let path = dir.join(path);
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, content).unwrap();
}

/// A source tree committed once, as the tool image leaves it, and its baseline.
fn task() -> (TempDir, Baseline) {
    let dir = TempDir::new().unwrap();
    let src = dir.path();
    write(src, "lib.c", "int a;\nint b;\n");
    write(src, "sub/util.c", "void f(void) {}\n");
    write(src, "data.bin", [0u8, 1, 2, 3, 255]);
    write(src, ".gitignore", "/vendor/\n*.o\n");
    write(src, "vendor/dep.c", "vendored\n");
    git(src, &["init", "-q"]);
    git(src, &["add", "-A"]);
    git(src, &["commit", "-qm", "buggy commit"]);
    let baseline = Baseline::record(src).unwrap();
    (dir, baseline)
}

fn diff(baseline: &Baseline) -> String {
    String::from_utf8(baseline.diff().unwrap()).unwrap()
}

fn files_in(patch: &str) -> Vec<String> {
    patch
        .lines()
        .filter_map(|l| l.strip_prefix("diff --git a/"))
        .map(|l| l.split(" b/").next().unwrap().to_string())
        .collect()
}

/// Apply `patch` to a fresh export of the base commit and return that tree.
fn apply_to_base(baseline: &Baseline, patch: &[u8]) -> TempDir {
    let out = TempDir::new().unwrap();
    let archive = Command::new("git")
        .args(["--git-dir"])
        .arg(baseline.repo())
        .args(["archive", "--format=tar", baseline.base()])
        .output()
        .unwrap();
    assert!(archive.status.success());
    let mut tar = Command::new("tar")
        .args(["-x", "-C"])
        .arg(out.path())
        .stdin(std::process::Stdio::piped())
        .spawn()
        .unwrap();
    use std::io::Write;
    tar.stdin
        .take()
        .unwrap()
        .write_all(&archive.stdout)
        .unwrap();
    assert!(tar.wait().unwrap().success());
    fs::write(out.path().join("agent.patch"), patch).unwrap();
    git(out.path(), &["init", "-q"]);
    git(out.path(), &["apply", "--binary", "agent.patch"]);
    fs::remove_file(out.path().join("agent.patch")).unwrap();
    out
}

#[test]
fn nothing_changed_is_an_empty_diff() {
    let (_dir, baseline) = task();
    assert_eq!(diff(&baseline), "");
    assert_eq!(baseline.changed_files().unwrap(), vec![]);
    assert_eq!(baseline.commit_messages(), "");
}

#[test]
fn takes_unstaged_staged_deleted_and_new_files() {
    let (dir, baseline) = task();
    let src = dir.path();
    write(src, "lib.c", "int a;\nint c;\n");
    write(src, "sub/util.c", "void f(void) { return; }\n");
    git(src, &["add", "sub/util.c"]);
    fs::remove_file(src.join("data.bin")).unwrap();
    write(src, "new/fix.h", "#define SAFE 1\n");

    let patch = diff(&baseline);
    assert_eq!(
        files_in(&patch),
        ["data.bin", "lib.c", "new/fix.h", "sub/util.c"]
    );
    assert!(patch.contains("+#define SAFE 1"));
}

#[test]
fn leaves_out_ignored_files_and_nested_repositories() {
    let (dir, baseline) = task();
    let src = dir.path();
    write(src, "vendor/extra.c", "ignored\n");
    write(src, "sub/util.o", "object\n");
    write(src, "nested/n.c", "n\n");
    git(&src.join("nested"), &["init", "-q"]);
    git(&src.join("nested"), &["add", "-A"]);
    git(&src.join("nested"), &["commit", "-qm", "n"]);

    assert_eq!(diff(&baseline), "");
}

#[test]
fn takes_changes_before_and_after_the_agents_commits() {
    let (dir, baseline) = task();
    let src = dir.path();
    write(src, "lib.c", "int a;\nint committed;\n");
    write(src, "added.c", "committed file\n");
    git(src, &["add", "-A"]);
    git(src, &["commit", "-qm", "fix the bug", "-m", "in detail"]);
    write(src, "later.c", "never added\n");
    write(src, "sub/util.c", "changed after the commit\n");

    let patch = diff(&baseline);
    assert_eq!(
        files_in(&patch),
        ["added.c", "later.c", "lib.c", "sub/util.c"]
    );
    let messages = baseline.commit_messages();
    assert!(
        messages.contains("\nfix the bug\nin detail\n\n---"),
        "{messages}"
    );
}

#[test]
fn ignores_the_agents_history_and_repository() {
    let (dir, baseline) = task();
    let src = dir.path();
    write(src, "lib.c", "int fixed;\n");
    let expected = diff(&baseline);

    // Rewrite the only commit, then make the working tree its own history.
    git(src, &["commit", "-qa", "--amend", "-m", "rewritten"]);
    assert_eq!(diff(&baseline), expected);
    git(src, &["checkout", "-q", "--orphan", "other"]);
    git(src, &["commit", "-qm", "orphan"]);
    assert_eq!(diff(&baseline), expected);
    fs::remove_dir_all(src.join(".git")).unwrap();
    assert_eq!(diff(&baseline), expected);
    assert_eq!(baseline.commit_messages(), "");
}

#[test]
fn ignores_the_agents_git_configuration() {
    let (dir, baseline) = task();
    let src = dir.path();
    let marker = dir.path().join("hook-ran");
    let hook = dir.path().join("hook.sh");
    fs::write(&hook, format!("#!/bin/sh\ntouch {}\n", marker.display())).unwrap();
    fs::set_permissions(&hook, fs::Permissions::from_mode(0o755)).unwrap();
    let hook = hook.display().to_string();
    git(src, &["config", "core.fsmonitor", &hook]);
    git(src, &["config", "diff.external", &hook]);
    git(src, &["config", "diff.noprefix", "true"]);
    git(src, &["config", "diff.evil.textconv", &hook]);
    git(src, &["config", "filter.evil.clean", &hook]);
    write(src, ".gitattributes", "*.c diff=evil filter=evil\n");
    write(src, "lib.c", "int fixed;\n");
    write(src, "new.c", "int new;\n");

    let patch = diff(&baseline);
    assert!(
        !marker.exists(),
        "a command from the agent's repository ran"
    );
    assert!(patch.contains("--- a/lib.c\n+++ b/lib.c\n"), "{patch}");
    assert!(patch.contains("+int fixed;"));
}

#[test]
fn keeps_binary_files_and_symlinks() {
    let (dir, baseline) = task();
    let src = dir.path();
    write(src, "data.bin", [9u8, 0, 8, 0, 7]);
    write(src, "new.bin", [0u8, 159, 146, 150]);
    symlink("/etc/hostname", src.join("link")).unwrap();

    let patch = diff(&baseline);
    assert!(patch.contains("GIT binary patch"));
    assert!(patch.contains("new file mode 120000"));
    assert!(patch.contains("\n+/etc/hostname\n"));

    let applied = apply_to_base(&baseline, patch.as_bytes());
    assert_eq!(
        fs::read(applied.path().join("new.bin")).unwrap(),
        [0u8, 159, 146, 150]
    );
    assert_eq!(
        fs::read(applied.path().join("data.bin")).unwrap(),
        [9u8, 0, 8, 0, 7]
    );
    assert_eq!(
        fs::read_link(applied.path().join("link")).unwrap(),
        Path::new("/etc/hostname")
    );
}

#[test]
fn the_patch_rebuilds_the_working_tree_from_the_base() {
    let (dir, baseline) = task();
    let src = dir.path();
    write(src, "lib.c", "int a;\nint b;\nint c;\n");
    write(src, "odd name [x]*.c", "literal pathspec\n");
    write(src, "sub/new dir/é.c", "unicode\n");
    fs::set_permissions(src.join("sub/util.c"), fs::Permissions::from_mode(0o755)).unwrap();
    git(src, &["add", "-A"]);
    git(src, &["commit", "-qm", "partial"]);
    fs::remove_file(src.join("lib.c")).unwrap();

    let applied = apply_to_base(&baseline, &baseline.diff().unwrap());
    for path in [
        "odd name [x]*.c",
        "sub/new dir/é.c",
        "sub/util.c",
        "data.bin",
    ] {
        assert_eq!(
            fs::read(applied.path().join(path)).unwrap(),
            fs::read(src.join(path)).unwrap(),
            "{path}"
        );
    }
    assert!(!applied.path().join("lib.c").exists());
    let mode = fs::metadata(applied.path().join("sub/util.c"))
        .unwrap()
        .permissions()
        .mode();
    assert_eq!(mode & 0o111, 0o111);
}

#[test]
fn repeated_captures_agree_and_store_no_content() {
    let (dir, baseline) = task();
    let src = dir.path();
    write(src, "lib.c", "int fixed;\n");
    write(src, "big.bin", vec![7u8; 1 << 20]);
    let stored = || {
        let out = Command::new("du")
            .args(["-sk"])
            .arg(baseline.repo().join("objects"))
            .output()
            .unwrap();
        let kib = String::from_utf8_lossy(&out.stdout);
        kib.split_whitespace()
            .next()
            .unwrap()
            .parse::<u64>()
            .unwrap()
    };
    let before = stored();

    let first = baseline.diff().unwrap();
    assert_eq!(baseline.diff().unwrap(), first);
    // New files are listed without their content; at most git's empty blob is added.
    assert!(stored() <= before + 8, "{} KiB -> {} KiB", before, stored());

    fs::remove_file(src.join("big.bin")).unwrap();
    assert_eq!(files_in(&diff(&baseline)), ["lib.c"]);
}

#[test]
fn lists_the_changed_files_with_line_counts() {
    let (dir, baseline) = task();
    let src = dir.path();
    write(src, "lib.c", "int a;\nint c;\nint d;\n");
    fs::remove_file(src.join("sub/util.c")).unwrap();
    write(src, "new.c", "one\ntwo\n");
    write(src, "data.bin", [5u8, 0, 5]);

    let file = |path: &str, status: &str, additions, deletions| ChangedFile {
        path: path.into(),
        status: status.into(),
        additions,
        deletions,
    };
    assert_eq!(
        baseline.changed_files().unwrap(),
        vec![
            file("data.bin", "modified", 0, 0),
            file("lib.c", "modified", 2, 1),
            file("new.c", "added", 2, 0),
            file("sub/util.c", "deleted", 0, 1),
        ]
    );
}
