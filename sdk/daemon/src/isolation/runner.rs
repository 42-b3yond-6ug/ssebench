use std::ffi::OsStr;
use std::fs;
use std::io;
use std::os::unix::fs::{PermissionsExt, lchown};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::Command;

use anyhow::{Context, Result, bail};

use super::account::Account;
use super::exec::{kill_all_processes_of, run_captured};
use super::fs::{Owner, copy_file, copy_tree, remove_tree};
use super::task_files::TaskFiles;
use crate::util::{ScriptOutput, log_script};

/// Name of the root-only store of support directories in the scratch root.
const PRISTINE: &str = "pristine";

/// Where [`TaskFiles`] keeps the support directories for a scratch root.
pub fn pristine_dir(root: &Path) -> PathBuf {
    root.join(PRISTINE)
}

/// Runs the task's scripts as the unprivileged runner account.
///
/// Each check gets a workspace in the scratch root: a private copy of what it
/// needs, owned by the runner. The scratch root is `root:<runner group>` with
/// mode 0710, so the runner can reach its workspaces and nobody else, the
/// agent included, can. Root prepares a workspace before the check and reads
/// its output after every process of the runner has been killed.
///
/// A session is the runner's home directory, with the build caches that the
/// checks share. Grading starts a new session, so nothing that code run
/// during `test_patch` left behind (a cache entry, a file in a support
/// directory, a process) takes part in grading.
pub struct TaskRunner {
    account: Option<Account>,
    root: PathBuf,
    task_files: Option<TaskFiles>,
    home: PathBuf,
    next: u64,
}

/// A check's private directory; removed when dropped.
#[derive(Debug)]
pub struct Workspace {
    path: PathBuf,
}

impl Workspace {
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Where the project copy goes; checks run with this as their directory.
    pub fn src(&self) -> PathBuf {
        self.path.join("src")
    }
}

impl Drop for Workspace {
    fn drop(&mut self) {
        if let Err(e) = remove_tree(&self.path) {
            log::warn!("failed to remove workspace {}: {e}", self.path.display());
        }
    }
}

impl TaskRunner {
    /// Run checks as `account`, in workspaces under `root`. The daemon must
    /// run as root.
    pub fn privileged(account: Account, root: &Path, task_files: TaskFiles) -> Result<Self> {
        if account.is_privileged_or_self() {
            bail!(
                "the task runner account {} (uid {}) must be an unprivileged user other than the daemon's",
                account.name,
                account.uid
            );
        }
        kill_all_processes_of(&account)?;
        fs::create_dir_all(root)?;
        lchown(root, Some(0), Some(account.gid))?;
        fs::set_permissions(root, fs::Permissions::from_mode(0o710))?;
        task_files
            .apply(&account)
            .context("failed to share the task files with the runner")?;
        let mut runner = Self {
            account: Some(account),
            root: root.to_path_buf(),
            task_files: Some(task_files),
            home: PathBuf::new(),
            next: 0,
        };
        runner.new_session()?;
        Ok(runner)
    }

    /// Run checks as the daemon's own user, for a daemon that is not root
    /// (tests and local development). Nothing is isolated.
    pub fn unprivileged(root: &Path) -> Result<Self> {
        fs::create_dir_all(root)?;
        let mut runner = Self {
            account: None,
            root: root.to_path_buf(),
            task_files: None,
            home: PathBuf::new(),
            next: 0,
        };
        runner.new_session()?;
        Ok(runner)
    }

    pub fn account(&self) -> Option<&Account> {
        self.account.as_ref()
    }

    pub fn home(&self) -> &Path {
        &self.home
    }

    fn owner(&self) -> Option<Owner> {
        self.account.as_ref().map(|a| (a.uid, a.gid))
    }

    fn id(&mut self) -> u64 {
        self.next += 1;
        self.next
    }

    /// Start over: kill the runner's processes, remove every workspace and
    /// the home directory, restore the support directories, and make a new
    /// home. Workspaces handed out before must not be used afterwards.
    pub fn new_session(&mut self) -> Result<()> {
        if let Some(account) = &self.account {
            kill_all_processes_of(account)?;
        }
        for entry in fs::read_dir(&self.root)? {
            let entry = entry?;
            if entry.file_name() != PRISTINE {
                remove_tree(&entry.path())?;
            }
        }
        if let Some(files) = &self.task_files {
            files.restore(self.owner())?;
        }
        let id = self.id();
        let home = self.root.join(format!("home-{id}"));
        self.make_dir(&home)?;
        self.make_dir(&home.join("tmp"))?;
        self.home = home;
        Ok(())
    }

    /// A new, empty workspace owned by the runner.
    pub fn workspace(&mut self) -> Result<Workspace> {
        let id = self.id();
        let path = self.root.join(format!("work-{id}"));
        self.make_dir(&path)?;
        Ok(Workspace { path })
    }

    /// Copy the project at `source` into the workspace's `src`.
    pub fn copy_source(&self, source: &Path, workspace: &Workspace) -> Result<PathBuf> {
        let dst = workspace.src();
        copy_tree(source, &dst, self.owner())
            .with_context(|| format!("failed to copy {}", source.display()))?;
        Ok(dst)
    }

    /// Copy a root-only directory into a workspace for one check.
    pub fn stage_dir(&self, source: &Path, dst: &Path) -> Result<()> {
        self.make_parents(dst)?;
        copy_tree(source, dst, self.owner())
            .with_context(|| format!("failed to stage {}", source.display()))
    }

    /// Copy a root-only file into a workspace for one check.
    pub fn stage_file(&self, source: &Path, dst: &Path, mode: u32) -> Result<()> {
        self.make_parents(dst)?;
        copy_file(source, dst, mode, self.owner())
            .with_context(|| format!("failed to stage {}", source.display()))
    }

    /// A command that runs as the runner, in its session.
    pub fn command(&self, program: impl AsRef<OsStr>) -> Command {
        let mut cmd = Command::new(program);
        let cache = self.home.join(".cache");
        cmd.env_remove("SSE_ADMIN_SOCKET")
            .env("HOME", &self.home)
            .env("TMPDIR", self.home.join("tmp"))
            .env("XDG_CACHE_HOME", &cache)
            .env("GOCACHE", cache.join("go-build"))
            .env("CCACHE_DIR", self.home.join(".ccache"));
        if let Some(account) = &self.account {
            cmd.uid(account.uid)
                .gid(account.gid)
                .env("USER", &account.name)
                .env("LOGNAME", &account.name);
        }
        cmd
    }

    /// Run a command from [`TaskRunner::command`], then kill every process of
    /// the runner, and log the result to the results directory.
    pub fn run(&self, cmd: Command) -> Result<ScriptOutput> {
        let description = format!("{cmd:?}");
        let output = run_captured(cmd, self.account.as_ref())
            .with_context(|| format!("failed to run {description}"))?;
        log_script(&description, &output);
        Ok(output)
    }

    fn make_dir(&self, path: &Path) -> Result<()> {
        fs::create_dir(path).with_context(|| format!("failed to create {}", path.display()))?;
        fs::set_permissions(path, fs::Permissions::from_mode(0o700))?;
        if let Some((uid, gid)) = self.owner() {
            lchown(path, Some(uid), Some(gid))?;
        }
        Ok(())
    }

    fn make_parents(&self, path: &Path) -> io::Result<()> {
        let Some(parent) = path.parent() else {
            return Ok(());
        };
        if parent.exists() {
            return Ok(());
        }
        self.make_parents(parent)?;
        fs::create_dir(parent)?;
        if let Some((uid, gid)) = self.owner() {
            lchown(parent, Some(uid), Some(gid))?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn workspaces_and_sessions() {
        let tmp = tempfile::tempdir().unwrap();
        let root = tmp.path().join("scratch");
        let mut runner = TaskRunner::unprivileged(&root).unwrap();
        let first_home = runner.home().to_path_buf();
        assert!(first_home.join("tmp").is_dir());

        let source = tmp.path().join("project");
        fs::create_dir(&source).unwrap();
        fs::write(source.join("main.c"), "int main(void) { return 0; }").unwrap();

        let ws = runner.workspace().unwrap();
        let src = runner.copy_source(&source, &ws).unwrap();
        assert!(src.join("main.c").is_file());
        runner
            .stage_file(
                &source.join("main.c"),
                &ws.path().join("in/deep/x.c"),
                0o640,
            )
            .unwrap();
        assert!(ws.path().join("in/deep/x.c").is_file());

        let mut cmd = runner.command("sh");
        cmd.args(["-c", "pwd; echo \"$HOME|$TMPDIR|$GOCACHE\"; ls"])
            .current_dir(&src);
        let out = runner.run(cmd).unwrap();
        assert!(out.success(), "{out:?}");
        let lines: Vec<&str> = out.stdout.lines().collect();
        assert_eq!(lines[0], src.to_str().unwrap());
        let home = first_home.display();
        assert_eq!(
            lines[1],
            format!("{home}|{home}/tmp|{home}/.cache/go-build")
        );
        assert_eq!(lines[2], "main.c");

        let path = ws.path().to_path_buf();
        drop(ws);
        assert!(!path.exists(), "a dropped workspace is removed");

        let kept = runner.workspace().unwrap();
        runner.new_session().unwrap();
        assert!(
            !kept.path().exists(),
            "a new session removes old workspaces"
        );
        assert!(!first_home.exists());
        assert_ne!(runner.home(), first_home);
        assert!(runner.home().join("tmp").is_dir());
    }

    #[test]
    fn the_admin_socket_is_not_passed_on() {
        let tmp = tempfile::tempdir().unwrap();
        let runner = TaskRunner::unprivileged(tmp.path()).unwrap();
        let mut cmd = runner.command("sh");
        cmd.args(["-c", "echo \"[${SSE_ADMIN_SOCKET:-}]\""])
            .env("SSE_ADMIN_SOCKET", "/run/ssebench/admin.sock");
        // An explicit env on the returned command wins; the runner's removal
        // covers the variable inherited from the daemon.
        cmd.env_remove("SSE_ADMIN_SOCKET");
        assert_eq!(runner.run(cmd).unwrap().stdout, "[]\n");
        assert!(
            runner
                .command("true")
                .get_envs()
                .any(|(k, v)| k == "SSE_ADMIN_SOCKET" && v.is_none())
        );
    }

    #[test]
    fn refuses_root_and_the_daemon_user_as_runner() {
        let tmp = tempfile::tempdir().unwrap();
        let root = Account {
            name: "root".into(),
            uid: 0,
            gid: 0,
            home: PathBuf::from("/root"),
        };
        let files = TaskFiles::empty(tmp.path());
        assert!(TaskRunner::privileged(root, tmp.path(), files).is_err());
    }
}
