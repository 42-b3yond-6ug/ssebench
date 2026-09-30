use std::env;
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};

use actix_web::dev::Server;
use actix_web::{App, HttpServer, middleware::Logger, web};
use env_logger::Env;
use log::info;

use ssebench::api::{Access, AppState, Difficulty, configure_routes, record_baseline};
use ssebench::bench::BenchCore;
use ssebench::isolation::{Account, TaskFiles, TaskRunner, is_root, pristine_dir};
use ssebench::shutdown;

/// Default HTTP port for WebUI access
const DEFAULT_HTTP_PORT: u16 = 4263;

/// Workers per listener (`SSE_DAEMON_WORKERS`). A tool call blocks its worker
/// until the command ends, so a few keep read-only routes answering during a
/// build. actix's default is one worker per host CPU for each listener, which
/// is 144 threads on a 48-core host, all of them idle.
const DEFAULT_WORKERS: usize = 4;

fn workers() -> usize {
    match env::var("SSE_DAEMON_WORKERS") {
        Ok(value) => match value.parse::<usize>() {
            Ok(n) if n > 0 => n,
            _ => {
                log::warn!("Ignoring SSE_DAEMON_WORKERS={value:?}: not a positive integer");
                DEFAULT_WORKERS
            }
        },
        Err(_) => DEFAULT_WORKERS,
    }
}

/// The runner account (`SSE_RUNNER_USER`) and its scratch root
/// (`SSE_RUNNER_DIR`). The tool layer creates the account.
const DEFAULT_RUNNER_USER: &str = "sse-runner";
const DEFAULT_RUNNER_DIR: &str = "/var/lib/ssebench-runner";

/// The task runner of a root daemon. Without the runner account the daemon
/// refuses to start rather than run the agent's code as root.
fn task_runner(bench: &BenchCore, bench_path: &Path) -> anyhow::Result<TaskRunner> {
    let user = env::var("SSE_RUNNER_USER").unwrap_or_else(|_| DEFAULT_RUNNER_USER.to_string());
    let root = PathBuf::from(
        env::var("SSE_RUNNER_DIR").unwrap_or_else(|_| DEFAULT_RUNNER_DIR.to_string()),
    );
    let account = Account::lookup(&user)?;
    let files = TaskFiles::plan(bench, bench_path, &pristine_dir(&root));
    info!(
        "Task scripts run as {} (uid {}) in {}; shared in place: {:?}, {:?}",
        account.name,
        account.uid,
        root.display(),
        files.scripts(),
        files.support_dirs()
    );
    TaskRunner::privileged(account, &root, files)
}

/// An `HttpServer` serving the API to callers with (`true`) or without
/// (`false`) privileged access. Signals are left to [`shutdown`], which stops
/// all servers together.
macro_rules! http_server {
    ($state:expr, $privileged:expr, $workers:expr) => {{
        let state = $state.clone();
        HttpServer::new(move || {
            App::new()
                .wrap(Logger::default())
                .app_data(web::Data::new(state.clone()))
                .app_data(web::Data::new(Access {
                    privileged: $privileged,
                }))
                .configure(configure_routes)
        })
        .workers($workers)
        .disable_signals()
        .shutdown_timeout(shutdown::GRACE.as_secs())
    }};
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    if matches!(env::args().nth(1).as_deref(), Some("--version" | "-V")) {
        println!("ssebench-daemon {}", env!("CARGO_PKG_VERSION"));
        return Ok(());
    }

    env_logger::Builder::from_env(
        Env::default().default_filter_or("info,actix_web::middleware::logger=warn"),
    )
    .init();

    let bench_path = env::var("SSE_BENCH_PATH").unwrap_or_else(|_| "/ssebench".to_string());
    let bench = BenchCore::new(&bench_path).expect("failed to load project");
    let difficulty = match Difficulty::from_env() {
        Ok(difficulty) => difficulty,
        Err(e) => {
            log::error!("{e}");
            std::process::exit(2);
        }
    };
    let state = if is_root() {
        let runner = task_runner(&bench, Path::new(&bench_path)).unwrap_or_else(|e| {
            log::error!("Cannot run task scripts unprivileged: {e:#}");
            std::process::exit(1);
        });
        AppState::with_runner(bench, difficulty, runner)
    } else {
        log::warn!("Not running as root: task scripts run as the daemon's own user");
        AppState::new(bench, difficulty)
    };
    info!("Difficulty gate: {:?}", state.difficulty);

    // Get HTTP port from environment or use default
    let http_port: u16 = env::var("SSE_HTTP_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(DEFAULT_HTTP_PORT);

    // Before any listener binds: the entrypoint starts the agent only once
    // the daemon's socket exists, so the tree is still as the image built it.
    record_baseline(state.project.source_folder());

    let workers = workers();
    info!("{workers} workers per listener");

    // Every listener is bound before the agent-facing one, whose socket the
    // entrypoint waits for. A listener other than that one that cannot bind is
    // left out; the daemon still serves the agent.
    let mut others: Vec<Server> = Vec::new();

    // Optional root-only admin socket for privileged callers (entrypoint and
    // evaluator): full grading, the reference patch, and phase changes.
    if let Ok(admin_socket) = env::var("SSE_ADMIN_SOCKET") {
        match admin_server(&state, &admin_socket, workers) {
            Ok(server) => {
                info!("Admin socket (privileged, 0600) started at {admin_socket}");
                others.push(server);
            }
            Err(e) => log::error!("Admin socket {admin_socket} not started: {e}"),
        }
    } else {
        info!("SSE_ADMIN_SOCKET not set; no privileged admin socket");
    }

    // Check if Unix socket mode is requested (for Python client compatibility)
    let main_server = if let Ok(socket_path) = env::var("SSE_DAEMON_SOCKET") {
        // Dual mode: Unix socket (primary for Python) + HTTP (for WebUI)
        info!("Starting in dual mode:");
        info!("  - Unix socket: {}", socket_path);
        info!("  - HTTP: 0.0.0.0:{}", http_port);

        // HTTP server in the background for WebUI access
        match http_server!(state, false, workers).bind(("0.0.0.0", http_port)) {
            Ok(server) => {
                info!("HTTP server started on 0.0.0.0:{}", http_port);
                others.push(server.run());
            }
            Err(e) => log::error!("HTTP server not started: {e}"),
        }

        let server = http_server!(state, false, workers).bind_uds(&socket_path)?;

        // Set socket permissions to 0666 (world read/write) so model user can connect
        // Agents run as non-root 'model' user (uid 1000) and need socket access
        let perms = fs::Permissions::from_mode(0o666);
        fs::set_permissions(&socket_path, perms)?;
        info!("Socket permissions set to 0666");

        info!("Unix socket server started at {}", socket_path);
        server.run()
    } else {
        // HTTP-only mode (for testing or standalone use)
        info!("Starting in HTTP-only mode on 0.0.0.0:{}", http_port);

        http_server!(state, false, workers)
            .bind(("0.0.0.0", http_port))?
            .run()
    };

    shutdown::run(main_server, others).await
}

/// The admin socket, readable and writable by root only: the `model` user
/// must not reach it.
fn admin_server(state: &AppState, path: &str, workers: usize) -> std::io::Result<Server> {
    let server = http_server!(state, true, workers).bind_uds(path)?;
    fs::set_permissions(path, fs::Permissions::from_mode(0o600))?;
    Ok(server.run())
}
