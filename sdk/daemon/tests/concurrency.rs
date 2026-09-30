//! The daemon serves concurrent requests with a small, fixed number of
//! workers per listener. These tests run the real binary.

mod common;

use std::process::Stdio;
use std::thread;
use std::time::{Duration, Instant};

use common::{post_to, start, thread_count};

const BUILD: &str = "sleep 1";

fn body_of(response: &str) -> &str {
    response.split_once("\r\n\r\n").map_or("", |(_, body)| body)
}

#[test]
fn concurrent_tool_calls_all_complete() {
    let daemon = start(Stdio::null(), &[], BUILD);
    let started = Instant::now();

    let calls: Vec<_> = (0..12)
        .map(|i| {
            let socket = daemon.agent_socket();
            thread::spawn(move || {
                if i % 4 == 0 {
                    post_to(
                        &socket,
                        "/tool/bencher?action=build",
                        r#"{"grading": false}"#,
                    )
                } else {
                    post_to(
                        &socket,
                        "/tool/bash?action=execute",
                        &format!(r#"{{"command": "echo call-{i}"}}"#),
                    )
                }
            })
        })
        .collect();

    for (i, call) in calls.into_iter().enumerate() {
        let response = call.join().unwrap();
        assert!(response.starts_with("HTTP/1.1 200"), "call {i}: {response}");
        if i % 4 != 0 {
            assert!(
                body_of(&response).contains(&format!("call-{i}")),
                "call {i}: {response}"
            );
        }
    }
    assert!(started.elapsed() < Duration::from_secs(60));
    drop(daemon);
}

#[test]
fn the_worker_count_is_fixed_and_configurable() {
    let default = start(Stdio::null(), &[], BUILD);
    let with_default = thread_count(&default);
    drop(default);

    let one = start(Stdio::null(), &[("SSE_DAEMON_WORKERS", "1")], BUILD);
    let with_one = thread_count(&one);
    drop(one);

    // One worker per host CPU for each of three listeners would be 144 threads
    // on a 48-core host; the default is a few per listener.
    assert!(with_default < 48, "{with_default} threads by default");
    assert!(with_one < with_default, "{with_one} vs {with_default}");
}
