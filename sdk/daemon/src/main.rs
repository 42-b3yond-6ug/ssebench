use std::env;
use std::fs;
use std::os::unix::fs::PermissionsExt;

use actix_web::{App, HttpServer, middleware::Logger, web};
use env_logger::Env;
use log::info;

use ssebench::api::{AppState, configure_routes};
use ssebench::bench::BenchCore;

/// Default HTTP port for WebUI access
const DEFAULT_HTTP_PORT: u16 = 4263;

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
    let state = AppState::new(bench);

    // Get HTTP port from environment or use default
    let http_port: u16 = env::var("SSE_HTTP_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(DEFAULT_HTTP_PORT);

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
                .configure(configure_routes)
        })
        .bind(("0.0.0.0", http_port))?;

        server.run().await
    }
}
