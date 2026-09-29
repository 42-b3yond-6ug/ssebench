use std::env;
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};

use actix_web::{App, HttpServer, middleware::Logger, web};
use env_logger::Env;
use log::info;

use ssebench::api::{Access, AppState, Difficulty, configure_routes, record_baseline};
use ssebench::bench::BenchCore;
use ssebench::isolation::{Account, TaskFiles, TaskRunner, is_root, pristine_dir};

/// Default HTTP port for WebUI access
const DEFAULT_HTTP_PORT: u16 = 4263;

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

    // Optional root-only admin socket for privileged callers (entrypoint and
    // evaluator): full grading, the reference patch, and phase changes.
    if let Ok(admin_socket) = env::var("SSE_ADMIN_SOCKET") {
        let admin_state = state.clone();
        tokio::spawn(async move {
            let admin_server = HttpServer::new(move || {
                App::new()
                    .wrap(Logger::default())
                    .app_data(web::Data::new(admin_state.clone()))
                    .app_data(web::Data::new(Access { privileged: true }))
                    .configure(configure_routes)
            })
            .bind_uds(&admin_socket)
            .expect("Failed to bind admin socket");

            // Root-only: the unprivileged `model` user must not reach this socket.
            let perms = fs::Permissions::from_mode(0o600);
            fs::set_permissions(&admin_socket, perms).expect("Failed to chmod admin socket");
            info!(
                "Admin socket (privileged, 0600) started at {}",
                admin_socket
            );

            if let Err(e) = admin_server.run().await {
                log::error!("Admin socket server error: {}", e);
            }
        });
    } else {
        info!("SSE_ADMIN_SOCKET not set; no privileged admin socket");
    }

    // Check if Unix socket mode is requested (for Python client compatibility)
    if let Ok(socket_path) = env::var("SSE_DAEMON_SOCKET") {
        // Dual mode: Unix socket (primary for Python) + HTTP (for WebUI)
        info!("Starting in dual mode:");
        info!("  - Unix socket: {}", socket_path);
        info!("  - HTTP: 0.0.0.0:{}", http_port);

        // Clone state for HTTP server
        let http_state = state.clone();

        // Spawn HTTP server in background for WebUI access
        tokio::spawn(async move {
            let http_server = HttpServer::new(move || {
                App::new()
                    .wrap(Logger::default())
                    .app_data(web::Data::new(http_state.clone()))
                    .app_data(web::Data::new(Access { privileged: false }))
                    .configure(configure_routes)
            })
            .bind(("0.0.0.0", http_port))
            .expect("Failed to bind HTTP server");

            info!("HTTP server started on 0.0.0.0:{}", http_port);

            if let Err(e) = http_server.run().await {
                log::error!("HTTP server error: {}", e);
            }
        });

        // Run Unix socket server as main (blocks until shutdown)
        let socket_server = HttpServer::new(move || {
            App::new()
                .wrap(Logger::default())
                .app_data(web::Data::new(state.clone()))
                .app_data(web::Data::new(Access { privileged: false }))
                .configure(configure_routes)
        })
        .bind_uds(&socket_path)?;

        // Set socket permissions to 0666 (world read/write) so model user can connect
        // Agents run as non-root 'model' user (uid 1000) and need socket access
        let perms = fs::Permissions::from_mode(0o666);
        fs::set_permissions(&socket_path, perms)?;
        info!("Socket permissions set to 0666");

        info!("Unix socket server started at {}", socket_path);
        socket_server.run().await
    } else {
        // HTTP-only mode (for testing or standalone use)
        info!("Starting in HTTP-only mode on 0.0.0.0:{}", http_port);

        let server = HttpServer::new(move || {
            App::new()
                .wrap(Logger::default())
                .app_data(web::Data::new(state.clone()))
                .app_data(web::Data::new(Access { privileged: false }))
                .configure(configure_routes)
        })
        .bind(("0.0.0.0", http_port))?;

        server.run().await
    }
}
