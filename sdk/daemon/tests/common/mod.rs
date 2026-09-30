//! Helpers for the tests that run the daemon binary.
#![allow(dead_code)]

use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::process::{Child, Command, ExitStatus, Stdio};
use std::thread;
use std::time::{Duration, Instant};

use tempfile::TempDir;

pub struct Daemon {
    pub child: Child,
    pub dir: TempDir,
    pub http_port: u16,
}

impl Daemon {
    pub fn agent_socket(&self) -> std::path::PathBuf {
        self.dir.path().join("agent.sock")
    }

    pub fn admin_socket(&self) -> std::path::PathBuf {
        self.dir.path().join("admin.sock")
    }

    pub fn signal(&self, signal: libc::c_int) {
        // SAFETY: kill has no memory-safety preconditions.
        let rc = unsafe { libc::kill(self.child.id() as i32, signal) };
        assert_eq!(rc, 0, "kill failed");
    }

    /// Wait for the daemon to exit, or kill it and fail the test.
    pub fn wait_exit(&mut self, within: Duration) -> (ExitStatus, Duration) {
        let start = Instant::now();
        loop {
            if let Some(status) = self.child.try_wait().unwrap() {
                return (status, start.elapsed());
            }
            if start.elapsed() > within {
                let _ = self.child.kill();
                let _ = self.child.wait();
                panic!("the daemon was still running {within:?} after the signal");
            }
            thread::sleep(Duration::from_millis(20));
        }
    }
}

impl Drop for Daemon {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

pub fn free_port() -> u16 {
    TcpListener::bind(("127.0.0.1", 0))
        .unwrap()
        .local_addr()
        .unwrap()
        .port()
}

/// A task whose build script writes its process id and then sleeps.
fn write_task(dir: &Path, build_body: &str) {
    let source = dir.join("src");
    fs::create_dir_all(dir.join("scripts")).unwrap();
    fs::create_dir(&source).unwrap();
    // An invalid gitfile makes every git command fail at once.
    fs::write(source.join(".git"), "not a gitdir\n").unwrap();
    fs::write(source.join("main.c"), "int main(void) { return 0; }\n").unwrap();
    fs::write(dir.join("patch.diff"), "--- a/f\n+++ b/f\n").unwrap();
    let build = dir.join("scripts/build.sh");
    fs::write(&build, format!("#!/bin/sh\n{build_body}\n")).unwrap();
    fs::set_permissions(&build, fs::Permissions::from_mode(0o755)).unwrap();
    fs::write(
        dir.join("config.yaml"),
        format!(
            "id: shutdown\nproject: shutdown\nlanguage: c\nsource: {}\n\
             task_description:\n  bug_description: test\n\
             scripts:\n  build: scripts/build.sh\nfiles:\n  patch: patch.diff\n",
            source.display()
        ),
    )
    .unwrap();
}

/// Start the daemon with the given `stderr`, extra environment and build script body.
pub fn start(stderr: Stdio, env: &[(&str, &str)], build: &str) -> Daemon {
    let dir = TempDir::new().unwrap();
    write_task(dir.path(), build);
    let http_port = free_port();
    let mut command = Command::new(env!("CARGO_BIN_EXE_ssebench-daemon"));
    command
        .env("SSE_BENCH_PATH", dir.path())
        .env("SSE_DAEMON_SOCKET", dir.path().join("agent.sock"))
        .env("SSE_ADMIN_SOCKET", dir.path().join("admin.sock"))
        .env("SSE_HTTP_PORT", http_port.to_string())
        .env("SSE_RUNNER_DIR", dir.path().join("runner"))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(stderr);
    command.envs(env.iter().copied());
    let child = command.spawn().unwrap();
    let daemon = Daemon {
        child,
        dir,
        http_port,
    };
    let deadline = Instant::now() + Duration::from_secs(30);
    while !(daemon.agent_socket().exists() && daemon.admin_socket().exists()) {
        assert!(Instant::now() < deadline, "the daemon did not start");
        thread::sleep(Duration::from_millis(20));
    }
    // The HTTP listener binds before the agent socket, but be sure.
    while TcpStream::connect(("127.0.0.1", http_port)).is_err() {
        assert!(Instant::now() < deadline, "the HTTP listener did not start");
        thread::sleep(Duration::from_millis(20));
    }
    daemon
}

/// One request on an open connection; the connection stays open.
pub fn get_version<S: Read + Write>(stream: &mut S) {
    stream
        .write_all(b"GET /version HTTP/1.1\r\nHost: daemon\r\n\r\n")
        .unwrap();
    let mut seen = Vec::new();
    let mut buf = [0u8; 1024];
    while !seen.windows(4).any(|w| w == b"\r\n\r\n") {
        let n = stream.read(&mut buf).unwrap();
        assert!(n > 0, "the daemon closed the connection early");
        seen.extend_from_slice(&buf[..n]);
    }
    assert!(
        seen.starts_with(b"HTTP/1.1 200"),
        "{}",
        String::from_utf8_lossy(&seen)
    );
}

/// Keep-alive connections to all three listeners, each having served a request.
pub fn idle_clients(daemon: &Daemon) -> (TcpStream, UnixStream, UnixStream) {
    let mut http = TcpStream::connect(("127.0.0.1", daemon.http_port)).unwrap();
    let mut agent = UnixStream::connect(daemon.agent_socket()).unwrap();
    let mut admin = UnixStream::connect(daemon.admin_socket()).unwrap();
    get_version(&mut http);
    get_version(&mut agent);
    get_version(&mut admin);
    (http, agent, admin)
}

/// Start the build script through the daemon and wait until it runs. Returns
/// the connection of the pending request and the script's process id.
pub fn start_build(daemon: &Daemon) -> (UnixStream, i32) {
    let mut conn = UnixStream::connect(daemon.agent_socket()).unwrap();
    let body = r#"{"grading": false}"#;
    write!(
        conn,
        "POST /tool/bencher?action=build HTTP/1.1\r\nHost: daemon\r\n\
         Content-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",
        body.len()
    )
    .unwrap();
    let pid_file = daemon.dir.path().join("build.pid");
    let deadline = Instant::now() + Duration::from_secs(30);
    loop {
        if let Some(pid) = fs::read_to_string(&pid_file)
            .ok()
            .and_then(|s| s.trim().parse().ok())
        {
            return (conn, pid);
        }
        assert!(Instant::now() < deadline, "the build script did not start");
        thread::sleep(Duration::from_millis(20));
    }
}

pub fn is_running(pid: i32) -> bool {
    match fs::read_to_string(format!("/proc/{pid}/stat")) {
        // A zombie has exited; its parent (or init) has not collected it yet.
        Ok(stat) => !stat
            .rsplit_once(") ")
            .is_some_and(|(_, rest)| rest.starts_with('Z')),
        Err(_) => false,
    }
}

/// POST `body` to `path` on a fresh connection to the agent socket and return
/// the whole response.
pub fn post(daemon: &Daemon, path: &str, body: &str) -> String {
    post_to(&daemon.agent_socket(), path, body)
}

/// [`post`] for a caller that has only the socket path.
pub fn post_to(socket: &Path, path: &str, body: &str) -> String {
    let mut conn = UnixStream::connect(socket).unwrap();
    write!(
        conn,
        "POST {path} HTTP/1.1\r\nHost: daemon\r\nConnection: close\r\n\
         Content-Type: application/json\r\nContent-Length: {}\r\n\r\n{body}",
        body.len()
    )
    .unwrap();
    let mut response = String::new();
    conn.read_to_string(&mut response).unwrap();
    response
}

/// The number of threads of the daemon process once it has stopped changing:
/// actix starts its workers after the listeners accept connections, so a count
/// taken as soon as `start` returns can miss some of them.
pub fn thread_count(daemon: &Daemon) -> usize {
    let count = || {
        fs::read_dir(format!("/proc/{}/task", daemon.child.id()))
            .unwrap()
            .count()
    };
    let deadline = Instant::now() + Duration::from_secs(10);
    let mut last = count();
    let mut unchanged = 0;
    while unchanged < 10 {
        assert!(Instant::now() < deadline, "the thread count did not settle");
        thread::sleep(Duration::from_millis(50));
        let now = count();
        if now == last {
            unchanged += 1;
        } else {
            (last, unchanged) = (now, 0);
        }
    }
    last
}
