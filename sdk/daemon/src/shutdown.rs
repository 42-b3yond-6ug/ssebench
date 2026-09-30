//! One path that stops every listener of the daemon.
//!
//! The listeners run with actix's own signal handling off. [`run`] serves
//! them, stops all of them together on SIGTERM, SIGINT or SIGQUIT, and returns
//! within a bound however the stop goes. A separate deadline ends the process
//! if even that does not happen.

use std::io;
use std::thread;
use std::time::Duration;

use actix_web::dev::Server;
use actix_web::rt::time::timeout;
use actix_web::rt::{self, signal::unix::SignalKind};
use tokio::sync::mpsc;

use crate::isolation::kill_live_groups;

/// How long a listener waits for open connections after it is told to stop.
/// SDK clients keep connections alive, so actix's 30 s default would outlast
/// the entrypoint's wait for the daemon to exit.
pub const GRACE: Duration = Duration::from_secs(2);

/// How long [`run`] waits for the listeners to report that they stopped,
/// counted from the stop request. Under heavy load a listener has been seen
/// not to report at all although its threads had ended, so the wait is bounded;
/// a listener that does not report is left behind when the process exits.
const STOP_WAIT: Duration = Duration::from_secs(3);

/// When the process ends whatever has not finished, counted from the stop
/// request. A handler blocked on a child or on a full log pipe holds its
/// worker thread, and the listener cannot stop that thread.
pub const DEADLINE: Duration = Duration::from_secs(4);

/// Exit status of a stop that ran into [`DEADLINE`].
const FORCED_EXIT: i32 = 1;

enum Event {
    Signal(SignalKind),
    MainEnded,
}

/// Serve `main` and `others` until `main` ends or a stop signal arrives, then
/// stop them all. The result is that of `main`, or `Ok` if it did not end.
///
/// `main` is the agent-facing listener; the daemon has no purpose without it.
pub async fn run(main: Server, others: Vec<Server>) -> io::Result<()> {
    let mut handles: Vec<_> = others.iter().map(Server::handle).collect();
    handles.push(main.handle());

    let (tx, mut rx) = mpsc::unbounded_channel();
    for kind in [
        SignalKind::terminate(),
        SignalKind::interrupt(),
        SignalKind::quit(),
    ] {
        let mut stream = rt::signal::unix::signal(kind)?;
        let tx = tx.clone();
        rt::spawn(async move {
            stream.recv().await;
            let _ = tx.send(Event::Signal(kind));
        });
    }
    let main = rt::spawn(async move {
        let result = main.await;
        let _ = tx.send(Event::MainEnded);
        result
    });
    let others: Vec<_> = others.into_iter().map(rt::spawn).collect();

    // Armed before anything is logged: the log is a pipe that can be full.
    let event = rx.recv().await;
    arm_deadline();
    let graceful = match event {
        Some(Event::Signal(kind)) => {
            log::info!("Received signal {}, shutting down", kind.as_raw_value());
            kind != SignalKind::quit()
        }
        _ => {
            log::warn!("The agent listener ended, shutting down");
            true
        }
    };

    // The children go first, so a request that waits for one finishes and the
    // listeners do not wait for it.
    kill_live_groups();
    let stopped = timeout(STOP_WAIT, async {
        let stops: Vec<_> = handles
            .into_iter()
            .map(|handle| rt::spawn(handle.stop(graceful)))
            .collect();
        for stop in stops {
            let _ = stop.await;
        }
        let result = main.await;
        for other in others {
            let _ = other.await;
        }
        result
    })
    .await;
    // A request may have started a child after the first kill.
    kill_live_groups();

    match stopped {
        Ok(Ok(result)) => result,
        Ok(Err(e)) => Err(io::Error::other(e)),
        Err(_) => {
            log::warn!("Listeners did not stop within {STOP_WAIT:?}; exiting");
            Ok(())
        }
    }
}

/// End the process with [`FORCED_EXIT`] after [`DEADLINE`]. It does not log:
/// a full log pipe is one of the things it guards against.
fn arm_deadline() {
    thread::spawn(|| {
        thread::sleep(DEADLINE);
        std::process::exit(FORCED_EXIT);
    });
}
