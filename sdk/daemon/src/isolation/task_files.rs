use std::collections::BTreeSet;
use std::fs;
use std::io;
use std::os::unix::fs::{PermissionsExt, lchown};
use std::path::{Path, PathBuf};

use super::account::Account;
use super::fs::{Owner, copy_tree, remove_tree};
use crate::bench::BenchCore;

/// What of the task directory (`/ssebench`) the runner may use.
///
/// The directory is root-only in the image. The runner gets exactly what the
/// build and test checks need in place:
///
/// - the build and test scripts, readable and executable, because test
///   scripts call the build script by its path; their content is public, the
///   agent's prompt shows it;
/// - support directories that the scripts use by path and write to, such as a
///   Rust harness at `/ssebench/harness`. They are copied to a root-only
///   store first, and restored from it before grading, so nothing a check
///   leaves in them reaches the grade.
///
/// Everything else (the config, the reference patch, the hidden tests, the
/// proofs of concept, the run script) stays root-only; the daemon stages a
/// copy into a check's workspace when that check needs it.
#[derive(Clone, Debug)]
pub struct TaskFiles {
    root: PathBuf,
    scripts: Vec<PathBuf>,
    support: Vec<PathBuf>,
    pristine: PathBuf,
}

impl TaskFiles {
    /// Work out the runner's share of the task directory `root`. Support
    /// directories are kept in `pristine`.
    pub fn plan(bench: &BenchCore, root: &Path, pristine: &Path) -> Self {
        let scripts = bench.scripts();
        let in_place: Vec<PathBuf> = [&scripts.build, &scripts.test]
            .into_iter()
            .flatten()
            .cloned()
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
        let texts: Vec<String> = [&scripts.build, &scripts.run, &scripts.test]
            .into_iter()
            .flatten()
            .filter_map(|p| fs::read_to_string(p).ok())
            .collect();

        let mut withheld: Vec<PathBuf> = bench.hidden_files();
        withheld.extend(in_place.iter().cloned());
        withheld.extend(scripts.run.iter().cloned());
        let support = referenced_dirs(root, &texts)
            .into_iter()
            .filter(|dir| dir.is_dir() && !withheld.iter().any(|f| f.starts_with(dir)))
            .collect();

        Self {
            root: root.to_path_buf(),
            scripts: in_place,
            support,
            pristine: pristine.to_path_buf(),
        }
    }

    /// A plan that shares nothing, for a task directory without scripts.
    pub fn empty(root: &Path) -> Self {
        Self {
            root: root.to_path_buf(),
            scripts: Vec::new(),
            support: Vec::new(),
            pristine: root.join(".pristine"),
        }
    }

    pub fn scripts(&self) -> &[PathBuf] {
        &self.scripts
    }

    pub fn support_dirs(&self) -> &[PathBuf] {
        &self.support
    }

    /// Set the permissions. Must run as root, before any check.
    pub fn apply(&self, runner: &Account) -> io::Result<()> {
        self.apply_with_owner(0, runner)
    }

    /// `apply`, with the opened directories and scripts owned by `owner`
    /// (root in production) and the runner's group.
    fn apply_with_owner(&self, owner: u32, runner: &Account) -> io::Result<()> {
        fs::create_dir_all(&self.pristine)?;
        fs::set_permissions(&self.pristine, fs::Permissions::from_mode(0o700))?;
        for dir in &self.support {
            let kept = self.pristine_of(dir);
            if !kept.exists() {
                copy_tree(dir, &kept, None)?;
            }
        }
        self.restore(Some((runner.uid, runner.gid)))?;

        let mut open: BTreeSet<PathBuf> = BTreeSet::from([self.root.clone()]);
        for script in &self.scripts {
            for dir in script.ancestors().skip(1) {
                if !dir.starts_with(&self.root) {
                    break;
                }
                open.insert(dir.to_path_buf());
            }
        }
        for dir in &open {
            lchown(dir, Some(owner), Some(runner.gid))?;
            fs::set_permissions(dir, fs::Permissions::from_mode(0o710))?;
            for entry in fs::read_dir(dir)? {
                let path = entry?.path();
                if open.contains(&path)
                    || self.scripts.contains(&path)
                    || self.support.contains(&path)
                {
                    continue;
                }
                let meta = fs::symlink_metadata(&path)?;
                if !meta.file_type().is_symlink() {
                    let mode = meta.permissions().mode() & 0o7700;
                    fs::set_permissions(&path, fs::Permissions::from_mode(mode))?;
                }
            }
        }
        for script in &self.scripts {
            lchown(script, Some(owner), Some(runner.gid))?;
            fs::set_permissions(script, fs::Permissions::from_mode(0o750))?;
        }
        Ok(())
    }

    /// Put every support directory back as the image had it, owned by `owner`.
    pub fn restore(&self, owner: Option<Owner>) -> io::Result<()> {
        for dir in &self.support {
            let kept = self.pristine_of(dir);
            if kept.exists() {
                remove_tree(dir)?;
                copy_tree(&kept, dir, owner)?;
            }
        }
        Ok(())
    }

    fn pristine_of(&self, dir: &Path) -> PathBuf {
        self.pristine
            .join(dir.file_name().unwrap_or(dir.as_os_str()))
    }
}

/// Top-level entries of `root` that the scripts name by absolute path.
fn referenced_dirs(root: &Path, scripts: &[String]) -> BTreeSet<PathBuf> {
    let prefix = format!("{}/", root.display());
    let mut found = BTreeSet::new();
    for text in scripts {
        let path_char = |c: char| c.is_ascii_alphanumeric() || matches!(c, '.' | '_' | '-');
        for (at, _) in text.match_indices(&prefix) {
            // `/x/ssebench/...` is another path.
            if text[..at]
                .chars()
                .next_back()
                .is_some_and(|c| path_char(c) || c == '/')
            {
                continue;
            }
            let name: String = text[at + prefix.len()..]
                .chars()
                .take_while(|&c| path_char(c))
                .collect();
            if !name.is_empty() && name != "." && name != ".." {
                found.insert(root.join(name));
            }
        }
    }
    found
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::MetadataExt;

    /// A task directory like the Rust tasks': a harness the scripts build in
    /// place, next to the reference patch and the proof of concept.
    fn task() -> (tempfile::TempDir, BenchCore) {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("ssebench");
        let source = dir.path().join("src");
        for sub in [
            "scripts",
            "diffs",
            "pocs/src",
            "harness/src",
            "reports",
            "mcp",
        ] {
            fs::create_dir_all(root.join(sub)).unwrap();
        }
        fs::create_dir_all(&source).unwrap();
        let r = root.display();
        fs::write(
            root.join("scripts/build.sh"),
            format!("cd {r}/harness\ncargo build\n"),
        )
        .unwrap();
        fs::write(
            root.join("scripts/test.sh"),
            format!("{r}/scripts/build.sh\ncargo test\n"),
        )
        .unwrap();
        fs::write(
            root.join("scripts/run.sh"),
            format!("cd {r}/harness && cargo run\n# {r}/pocs is staged\n"),
        )
        .unwrap();
        fs::write(root.join("harness/src/main.rs"), "fn main() {}").unwrap();
        fs::write(root.join("pocs/src/main.rs"), "fn main() {}").unwrap();
        fs::write(root.join("diffs/patch.diff"), "the answer").unwrap();
        fs::write(root.join("diffs/test.diff"), "hidden tests").unwrap();
        fs::write(root.join("reports/issue.md"), "report").unwrap();
        fs::write(
            root.join("config.yaml"),
            format!(
                "id: t\nproject: p\nlanguage: rust\nsource: {}\n\
                 task_description:\n  crash_report: [reports/issue.md]\n\
                 scripts:\n  build: scripts/build.sh\n  run: scripts/run.sh\n  test: scripts/test.sh\n\
                 files:\n  patch: diffs/patch.diff\n  future_test: diffs/test.diff\n  poc: [pocs/src/main.rs]\n",
                source.display()
            ),
        )
        .unwrap();
        let bench = BenchCore::new(&root).unwrap();
        (dir, bench)
    }

    #[test]
    fn finds_the_directories_the_scripts_name() {
        let root = Path::new("/ssebench");
        let found = referenced_dirs(
            root,
            &[
                "cd /ssebench/harness\n/ssebench/scripts/build.sh; ls /ssebench/ /ssebench/.. \"/ssebench/a-b.c\"".into(),
                "/ssebenchx/other /x/ssebench/y".into(),
            ],
        );
        let names: Vec<_> = found.iter().map(|p| p.display().to_string()).collect();
        assert_eq!(
            names,
            ["/ssebench/a-b.c", "/ssebench/harness", "/ssebench/scripts"]
        );
    }

    #[test]
    fn plans_scripts_and_support_dirs_but_never_hidden_material() {
        let (dir, bench) = task();
        let root = dir.path().join("ssebench");
        let files = TaskFiles::plan(&bench, &root, &dir.path().join("pristine"));
        assert_eq!(
            files.scripts(),
            [root.join("scripts/build.sh"), root.join("scripts/test.sh")]
        );
        // scripts/ holds the run script and pocs/ the proof of concept, so
        // neither is shared although the scripts name them.
        assert_eq!(files.support_dirs(), [root.join("harness")]);
    }

    #[test]
    fn apply_opens_only_the_runner_share_and_restore_undoes_changes() {
        let (dir, bench) = task();
        let root = dir.path().join("ssebench");
        let files = TaskFiles::plan(&bench, &root, &dir.path().join("pristine"));
        // Tests run without root: the directories stay ours, in our group.
        let meta = fs::metadata(dir.path()).unwrap();
        let me = Account {
            name: "me".into(),
            uid: meta.uid(),
            gid: meta.gid(),
            home: PathBuf::new(),
        };
        files.apply_with_owner(me.uid, &me).unwrap();
        let mode = |p: &str| fs::symlink_metadata(root.join(p)).unwrap().mode() & 0o777;
        assert_eq!(mode(""), 0o710);
        assert_eq!(mode("scripts"), 0o710);
        assert_eq!(mode("scripts/build.sh"), 0o750);
        assert_eq!(mode("scripts/test.sh"), 0o750);
        assert_eq!(mode("scripts/run.sh") & 0o077, 0);
        for withheld in ["diffs", "pocs", "reports", "mcp", "config.yaml"] {
            assert_eq!(mode(withheld) & 0o077, 0, "{withheld} is open to others");
        }

        // A check writes into the harness; restoring puts the image's copy back.
        fs::write(root.join("harness/planted"), "x").unwrap();
        fs::write(root.join("harness/src/main.rs"), "changed").unwrap();
        files.restore(None).unwrap();
        assert!(!root.join("harness/planted").exists());
        assert_eq!(
            fs::read_to_string(root.join("harness/src/main.rs")).unwrap(),
            "fn main() {}"
        );
    }
}
