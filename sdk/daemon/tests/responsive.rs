//! Read-only routes answer while a tool call runs. These tests run the real
//! binary.

mod common;

use std::io::{Read, Write};
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::process::Stdio;
use std::thread;
use std::time::{Duration, Instant};

use common::{post_to, start};

/// A read-only request may take this long, well under the tool call.
const ANSWERS_WITHIN: Duration = Duration::from_millis(900);

const TOOL_CALL: Duration = Duration::from_secs(5);

fn get(socket: &Path, path: &str) -> String {
    let mut conn = UnixStream::connect(socket).unwrap();
    // A daemon that does not answer fails the test instead of waiting for the
    // tool call to end.
    conn.set_read_timeout(Some(Duration::from_secs(2))).unwrap();
    write!(
        conn,
        "GET {path} HTTP/1.1\r\nHost: daemon\r\nConnection: close\r\n\r\n"
    )
    .unwrap();
    let mut response = String::new();
    conn.read_to_string(&mut response)
        .unwrap_or_else(|e| panic!("GET {path} got no answer: {e}"));
    response
}

fn status(response: &str) -> &str {
    response.lines().next().unwrap_or("")
}

#[test]
fn read_only_routes_answer_during_a_long_tool_call() {
    // One worker per listener: the tool call would hold it if it ran there.
    let daemon = start(Stdio::null(), &[("SSE_DAEMON_WORKERS", "1")], "true");
    let socket = daemon.agent_socket();

    let call = {
        let socket = socket.clone();
        thread::spawn(move || {
            let started = Instant::now();
            let response = post_to(
                &socket,
                "/tool/bash?action=execute",
                r#"{"command": "sleep 5; echo finished"}"#,
            );
            (response, started.elapsed())
        })
    };
    // Let the command start and hold the tool lock.
    thread::sleep(Duration::from_millis(500));

    // The task's git is unusable, so /diff and /files answer with an error;
    // what matters is that they answer.
    for (path, expected) in [
        ("/version", "200"),
        ("/capabilities", "200"),
        ("/agent/dialog", "200"),
        ("/diff", "500"),
        ("/files", "500"),
    ] {
        let started = Instant::now();
        let response = get(&socket, path);
        let took = started.elapsed();
        assert!(
            status(&response).contains(expected),
            "GET {path}: {response}"
        );
        assert!(took < ANSWERS_WITHIN, "GET {path} took {took:?}");
    }

    let (response, took) = call.join().unwrap();
    assert!(status(&response).contains("200"), "{response}");
    assert!(response.contains("finished"), "{response}");
    assert!(took >= TOOL_CALL - Duration::from_millis(100), "{took:?}");
}

#[test]
fn tool_calls_still_run_one_at_a_time() {
    let daemon = start(Stdio::null(), &[("SSE_DAEMON_WORKERS", "1")], "true");
    let socket = daemon.agent_socket();

    let started = Instant::now();
    let calls: Vec<_> = (0..2)
        .map(|_| {
            let socket = socket.clone();
            thread::spawn(move || {
                post_to(
                    &socket,
                    "/tool/bash?action=execute",
                    r#"{"command": "sleep 1"}"#,
                )
            })
        })
        .collect();
    for call in calls {
        assert!(status(&call.join().unwrap()).contains("200"));
    }
    // Two calls under one lock take the sum of their times.
    assert!(started.elapsed() >= Duration::from_millis(1900));
}
