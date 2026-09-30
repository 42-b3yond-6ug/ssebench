//! The daemon exits soon after SIGTERM, whatever its clients and task scripts
//! are doing. These tests run the real binary.

mod common;

use std::fs::File;
use std::io::Write;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::process::Stdio;
use std::thread;
use std::time::{Duration, Instant};

use common::{idle_clients, is_running, start, start_build};

/// The daemon's bound for stopping is 4 s; this leaves room for a loaded host.
const EXIT_WITHIN: Duration = Duration::from_secs(8);

/// A build script that records its process id and runs until killed.
const SLEEPING_BUILD: &str = "echo $$ > \"$(dirname \"$0\")/../build.pid\"\nexec sleep 120";

#[test]
fn exits_on_sigterm_with_keep_alive_clients_and_a_running_script() {
    let mut daemon = start(Stdio::null(), &[], SLEEPING_BUILD);
    let clients = idle_clients(&daemon);
    let (_build, script) = start_build(&daemon);
    assert!(is_running(script));

    daemon.signal(libc::SIGTERM);
    let (status, took) = daemon.wait_exit(EXIT_WITHIN);

    assert!(status.success(), "exit status {status:?} after {took:?}");
    assert!(took < EXIT_WITHIN);
    // The daemon does not leave the script running.
    let deadline = Instant::now() + Duration::from_secs(5);
    while is_running(script) {
        assert!(
            Instant::now() < deadline,
            "the build script is still running"
        );
        thread::sleep(Duration::from_millis(20));
    }
    drop(clients);
}

#[test]
fn exits_on_sigterm_with_a_running_and_a_waiting_build() {
    let mut daemon = start(Stdio::null(), &[], SLEEPING_BUILD);
    let (_build, script) = start_build(&daemon);
    // Waits for the tool lock that the build holds.
    let waiting = {
        let socket = daemon.agent_socket();
        thread::spawn(move || {
            common::post_to(
                &socket,
                "/tool/bencher?action=build",
                r#"{"grading": false}"#,
            )
        })
    };
    thread::sleep(Duration::from_millis(300));

    daemon.signal(libc::SIGTERM);
    let (status, took) = daemon.wait_exit(EXIT_WITHIN);

    assert!(status.success(), "exit status {status:?} after {took:?}");
    // Neither the running build nor the one that waited leaves a script.
    let latest: i32 = std::fs::read_to_string(daemon.dir.path().join("build.pid"))
        .unwrap()
        .trim()
        .parse()
        .unwrap();
    let deadline = Instant::now() + Duration::from_secs(5);
    while is_running(script) || is_running(latest) {
        assert!(Instant::now() < deadline, "a build script is still running");
        thread::sleep(Duration::from_millis(20));
    }
    let _ = waiting.join();
}

#[test]
fn exits_on_sigint() {
    let mut daemon = start(Stdio::null(), &[], SLEEPING_BUILD);
    let _clients = idle_clients(&daemon);
    daemon.signal(libc::SIGINT);
    let (status, _) = daemon.wait_exit(EXIT_WITHIN);
    assert!(status.success(), "exit status {status:?}");
}

/// A pipe that holds `capacity` bytes and is full. Returns the read end,
/// which the test keeps and never reads, and the write end for the child.
fn full_pipe(capacity: libc::c_int) -> (OwnedFd, OwnedFd) {
    let mut fds = [0; 2];
    // SAFETY: fds has room for the two descriptors pipe2 returns.
    assert_eq!(unsafe { libc::pipe2(fds.as_mut_ptr(), libc::O_CLOEXEC) }, 0);
    // SAFETY: pipe2 returned two open descriptors that nothing else owns.
    let (read, write) = unsafe { (OwnedFd::from_raw_fd(fds[0]), OwnedFd::from_raw_fd(fds[1])) };
    // SAFETY: plain fcntl calls on a descriptor that is open.
    assert!(unsafe { libc::fcntl(write.as_raw_fd(), libc::F_SETPIPE_SZ, capacity) } > 0);
    (read, write)
}

/// Fill the pipe through a second open file description, which is
/// non-blocking; the child's description keeps blocking.
fn fill(write: &OwnedFd) {
    let mut filler = File::options()
        .write(true)
        .open(format!("/proc/self/fd/{}", write.as_raw_fd()))
        .unwrap();
    // SAFETY: plain fcntl calls on a descriptor that is open.
    unsafe {
        let flags = libc::fcntl(filler.as_raw_fd(), libc::F_GETFL);
        libc::fcntl(filler.as_raw_fd(), libc::F_SETFL, flags | libc::O_NONBLOCK);
    }
    let chunk = [b'x'; 512];
    while filler.write(&chunk).is_ok() {}
}

#[test]
fn exits_when_its_log_pipe_is_full() {
    // A reader that never drains the log fills the pipe, and a write to it
    // blocks the thread that logs.
    let (_read, write) = full_pipe(4096);
    let mut daemon = start(Stdio::from(write.try_clone().unwrap()), &[], SLEEPING_BUILD);
    let _clients = idle_clients(&daemon);
    fill(&write);

    daemon.signal(libc::SIGTERM);
    let (_status, took) = daemon.wait_exit(EXIT_WITHIN);
    assert!(took < EXIT_WITHIN);
}
