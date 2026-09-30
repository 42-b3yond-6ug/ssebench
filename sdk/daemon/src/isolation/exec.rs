use std::io::{self, Read};
use std::os::unix::process::CommandExt;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Mutex, mpsc};
use std::thread;
use std::time::{Duration, Instant};

use super::account::Account;
use crate::util::ScriptOutput;

/// How long to keep reading output after the processes are gone. Only a
/// process that escaped every kill below can hold a pipe open that long.
const OUTPUT_GRACE: Duration = Duration::from_secs(10);

/// Rounds of killing before giving up on a user's processes.
const KILL_ROUNDS: usize = 20;

/// Process groups of children that are still running: the daemon kills them
/// when it stops, since it cannot wait for them.
static LIVE_GROUPS: Mutex<Vec<i32>> = Mutex::new(Vec::new());

/// Set by [`kill_live_groups`]. A tool call that waited for the tool lock
/// starts its child only after the daemon began to stop; that child is killed
/// as soon as it is tracked.
static STOPPING: AtomicBool = AtomicBool::new(false);

/// A child's process group, listed in [`kill_live_groups`] until dropped.
#[derive(Debug)]
pub struct TrackedGroup(i32);

impl TrackedGroup {
    /// Track the group `pgid`, which must be that of a child the caller
    /// waits for and started with `process_group(0)`.
    pub fn new(pgid: u32) -> Option<Self> {
        let pgid = i32::try_from(pgid).ok()?;
        let mut groups = LIVE_GROUPS.lock().unwrap();
        groups.push(pgid);
        if STOPPING.load(Ordering::SeqCst) {
            // SAFETY: see kill_process_group.
            unsafe {
                libc::kill(-pgid, libc::SIGKILL);
            }
        }
        Some(Self(pgid))
    }
}

impl Drop for TrackedGroup {
    fn drop(&mut self) {
        let mut groups = LIVE_GROUPS.lock().unwrap();
        if let Some(i) = groups.iter().position(|g| *g == self.0) {
            groups.swap_remove(i);
        }
    }
}

/// Kill every tracked process group. The waiters see their children exit.
pub fn kill_live_groups() {
    let groups = LIVE_GROUPS.lock().unwrap();
    STOPPING.store(true, Ordering::SeqCst);
    for pgid in groups.iter() {
        // SAFETY: see kill_process_group.
        unsafe {
            libc::kill(-pgid, libc::SIGKILL);
        }
    }
}

/// Run `cmd` to completion and capture its output.
///
/// The command runs in a new process group with stdin closed. Once it exits,
/// everything it left behind is killed before the output is collected: its
/// process group and, when `reap` is given, every process of that user, since
/// code that daemonises leaves the group. So no process of the check can still
/// write to the output, or to anything else, after this returns.
pub fn run_captured(mut cmd: Command, reap: Option<&Account>) -> io::Result<ScriptOutput> {
    cmd.stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .process_group(0);
    let mut child = cmd.spawn()?;
    let _group = TrackedGroup::new(child.id());
    let stdout = child.stdout.take().map(drain);
    let stderr = child.stderr.take().map(drain);

    let status = child.wait()?;
    kill_process_group(child.id());
    if let Some(account) = reap {
        kill_all_processes_of(account)?;
    }

    let deadline = Instant::now() + OUTPUT_GRACE;
    Ok(ScriptOutput::new(
        status.code().unwrap_or(-1),
        collect(stdout, deadline),
        collect(stderr, deadline),
    ))
}

enum Chunk {
    Data(Vec<u8>),
    Done,
}

/// Read a pipe on a thread, forwarding what arrives.
fn drain<R: Read + Send + 'static>(mut pipe: R) -> mpsc::Receiver<Chunk> {
    let (tx, rx) = mpsc::channel();
    thread::spawn(move || {
        let mut buf = [0u8; 64 * 1024];
        loop {
            match pipe.read(&mut buf) {
                Ok(0) | Err(_) => break,
                Ok(n) => {
                    if tx.send(Chunk::Data(buf[..n].to_vec())).is_err() {
                        return;
                    }
                }
            }
        }
        let _ = tx.send(Chunk::Done);
    });
    rx
}

fn collect(rx: Option<mpsc::Receiver<Chunk>>, deadline: Instant) -> String {
    let mut out = Vec::new();
    if let Some(rx) = rx {
        while let Ok(Chunk::Data(data)) =
            rx.recv_timeout(deadline.saturating_duration_since(Instant::now()))
        {
            out.extend_from_slice(&data);
        }
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn kill_process_group(pgid: u32) {
    if let Ok(pgid) = i32::try_from(pgid) {
        // SAFETY: kill has no memory-safety preconditions; a group that is
        // already gone returns ESRCH, which is fine.
        unsafe {
            libc::kill(-pgid, libc::SIGKILL);
        }
    }
}

/// Kill every process that runs as `account` and wait until none is left.
///
/// A helper forked as that user calls `kill(-1, SIGKILL)`, which signals all
/// of the user's processes in one step, so none can fork its way out. The
/// process table is then checked, and stragglers killed directly.
pub fn kill_all_processes_of(account: &Account) -> io::Result<()> {
    if account.is_privileged_or_self() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            format!("refusing to kill every process of uid {}", account.uid),
        ));
    }
    for round in 0..KILL_ROUNDS {
        kill_as(account);
        let left = processes_of(account.uid)?;
        if left.is_empty() {
            return Ok(());
        }
        for pid in left {
            // SAFETY: see kill_process_group.
            unsafe {
                libc::kill(pid, libc::SIGKILL);
            }
        }
        thread::sleep(Duration::from_millis(10 * (round as u64 + 1)));
    }
    let left = processes_of(account.uid)?;
    if left.is_empty() {
        Ok(())
    } else {
        Err(io::Error::other(format!(
            "processes of uid {} survived: {left:?}",
            account.uid
        )))
    }
}

fn kill_as(account: &Account) {
    let mut helper = Command::new("true");
    helper
        .uid(account.uid)
        .gid(account.gid)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    // SAFETY: the closure runs in the forked child after it has switched to
    // the account's uid, and only calls kill, which is async-signal-safe. On
    // Linux, kill(-1) does not signal the caller itself.
    unsafe {
        helper.pre_exec(|| {
            libc::kill(-1, libc::SIGKILL);
            Ok(())
        });
    }
    if let Err(e) = helper.status() {
        log::warn!("failed to run the kill helper as uid {}: {e}", account.uid);
    }
}

/// Live processes whose real, effective or saved uid is `uid`.
pub fn processes_of(uid: u32) -> io::Result<Vec<i32>> {
    let own = std::process::id() as i32;
    let mut pids = Vec::new();
    for entry in std::fs::read_dir("/proc")? {
        let entry = entry?;
        let Some(pid) = entry
            .file_name()
            .to_str()
            .and_then(|s| s.parse::<i32>().ok())
        else {
            continue;
        };
        if pid == own {
            continue;
        }
        // A process can exit between the listing and the read.
        let Ok(status) = std::fs::read_to_string(entry.path().join("status")) else {
            continue;
        };
        if status_matches(&status, uid) {
            pids.push(pid);
        }
    }
    Ok(pids)
}

/// Whether a `/proc/<pid>/status` belongs to a live process of `uid`. Zombies
/// no longer run and cannot be killed, so they do not count.
fn status_matches(status: &str, uid: u32) -> bool {
    let mut uids = None;
    let mut dead = false;
    for line in status.lines() {
        if let Some(state) = line.strip_prefix("State:") {
            dead = matches!(state.trim_start().chars().next(), Some('Z' | 'X'));
        } else if let Some(rest) = line.strip_prefix("Uid:") {
            uids = Some(
                rest.split_whitespace()
                    .take(3)
                    .filter_map(|u| u.parse::<u32>().ok())
                    .collect::<Vec<_>>(),
            );
        }
    }
    !dead && uids.is_some_and(|u| u.contains(&uid))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::isolation::account::effective_uid;
    use std::path::PathBuf;

    fn sh(script: &str) -> Command {
        let mut cmd = Command::new("sh");
        cmd.arg("-c").arg(script);
        cmd
    }

    #[test]
    fn captures_status_and_both_streams() {
        let out = run_captured(sh("echo out; echo err >&2; exit 3"), None).unwrap();
        assert_eq!(out.code, 3);
        assert_eq!(out.stdout, "out\n");
        assert_eq!(out.stderr, "err\n");
    }

    #[test]
    fn stdin_is_closed() {
        let out = run_captured(sh("cat; echo done"), None).unwrap();
        assert_eq!(out.stdout, "done\n");
    }

    #[test]
    fn background_processes_in_the_group_are_killed() {
        // Without the kill, the background sleep would hold stdout open and
        // collecting the output would wait for it.
        let started = Instant::now();
        let out = run_captured(sh("sleep 30 & echo started"), None).unwrap();
        assert_eq!(out.stdout, "started\n");
        assert!(started.elapsed() < Duration::from_secs(20));
    }

    #[test]
    fn refuses_to_reap_root_or_itself() {
        for uid in [0, effective_uid()] {
            let account = Account {
                name: "x".into(),
                uid,
                gid: uid,
                home: PathBuf::new(),
            };
            assert!(kill_all_processes_of(&account).is_err());
        }
    }

    #[test]
    fn status_parsing_matches_any_of_real_effective_and_saved_uid() {
        let status = |state: &str, uids: &str| {
            format!("Name:\tbash\nState:\t{state}\nPid:\t42\nUid:\t{uids}\nGid:\t0\t0\t0\t0\n")
        };
        assert!(status_matches(
            &status("S (sleeping)", "999\t999\t999\t999"),
            999
        ));
        assert!(status_matches(&status("R (running)", "999\t0\t0\t0"), 999));
        assert!(status_matches(&status("S (sleeping)", "0\t0\t999\t0"), 999));
        assert!(!status_matches(
            &status("S (sleeping)", "0\t0\t0\t999"),
            999
        ));
        assert!(!status_matches(
            &status("Z (zombie)", "999\t999\t999\t999"),
            999
        ));
        assert!(!status_matches(
            &status("S (sleeping)", "1000\t1000\t1000\t1000"),
            999
        ));
        assert!(!status_matches("Name:\tx\n", 999));
    }

    #[test]
    fn lists_its_own_children() {
        let mut child = Command::new("sleep").arg("30").spawn().unwrap();
        let pids = processes_of(effective_uid()).unwrap();
        assert!(pids.contains(&(child.id() as i32)));
        assert!(!pids.contains(&(std::process::id() as i32)));
        child.kill().unwrap();
        child.wait().unwrap();
    }
}
