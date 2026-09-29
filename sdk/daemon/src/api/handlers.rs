use std::process::Command;

use actix_web::{HttpResponse, web};
use anyhow::{Context, anyhow};
use log::debug;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::diff::get_full_diff;
use super::error::AppError;
use super::grading::prepare_grading;
use super::state::{Access, AppState};

#[derive(Serialize)]
struct AppVersion {
    version: String,
}

/// GET /version - Returns the application version.
async fn version() -> web::Json<AppVersion> {
    debug!("Received request: GET /version");
    web::Json(AppVersion {
        version: env!("CARGO_PKG_VERSION").into(),
    })
}

/// GET /project - Returns project metadata.
async fn project(state: web::Data<AppState>) -> HttpResponse {
    debug!("Received request: GET /project");
    HttpResponse::Ok().json(state.project.public_metadata())
}

/// GET /capabilities - Returns what operations are available for this case.
async fn capabilities(state: web::Data<AppState>) -> HttpResponse {
    debug!("Received request: GET /capabilities");
    HttpResponse::Ok().json(state.project.capabilities())
}

#[derive(Deserialize)]
struct ToolQuery {
    action: String,
}

/// POST /tool/{name} - Route request to the specified tool.
///
/// On the agent-facing listeners the `bencher` actions are gated by the
/// difficulty level: a level that withholds a check (e.g. the PoC at the
/// default `NO_FUTURE_TEST`) makes the corresponding action return 403. The
/// admin socket is privileged and never gated, so grading runs every check.
async fn tool(
    state: web::Data<AppState>,
    access: web::Data<Access>,
    path: web::Path<String>,
    query: web::Query<ToolQuery>,
    body: web::Json<Value>,
) -> Result<HttpResponse, AppError> {
    let name = path.into_inner();
    let action = query.into_inner().action;
    let arg = body.into_inner();

    debug!("Received request: POST /tool/{} action={}", name, action);

    if !access.privileged && name == "bencher" && !state.difficulty.allows_bencher_action(&action) {
        return Ok(HttpResponse::Forbidden().json(json!({
            "error": format!(
                "action '{}' is not available at the current difficulty level",
                action
            )
        })));
    }

    let mut tool_router = state.tool_router.lock().unwrap();

    tool_router
        .route(&name, &action, &arg)
        .map(|result| HttpResponse::Ok().json(result))
        .map_err(AppError::from)
}

// =============================================================================
// WebUI Endpoints - For real-time code change monitoring
// =============================================================================

/// GET /diff - Returns unified diff of working directory vs HEAD (buggy commit)
///
/// The source folder is expected to be a git repository with an initial "buggy commit".
/// This endpoint shows all uncommitted changes made by the agent, including:
/// - Staged changes (index vs HEAD)
/// - Unstaged changes (working tree vs index)
/// - New untracked files (as proper git patches)
async fn diff(state: web::Data<AppState>) -> Result<HttpResponse, AppError> {
    debug!("Received request: GET /diff");

    let source_folder = state.project.source_folder();
    let diff_text = get_full_diff(source_folder)?;

    Ok(HttpResponse::Ok().json(json!({
        "diff": diff_text
    })))
}

/// Response structure for a single changed file
#[derive(Serialize)]
struct ChangedFile {
    path: String,
    status: String,
    additions: u32,
    deletions: u32,
}

/// GET /files - Returns list of modified files with addition/deletion stats
///
/// Returns only files that have been modified since the initial "buggy commit".
/// Each file includes its path, status (modified/added/deleted), and line counts.
async fn files(state: web::Data<AppState>) -> Result<HttpResponse, AppError> {
    debug!("Received request: GET /files");

    let source_folder = state.project.source_folder();

    // Get modified files using git status --porcelain
    let status_output = Command::new("git")
        .args(["status", "--porcelain"])
        .current_dir(source_folder)
        .output()
        .context("Failed to execute git status command")?;

    if !status_output.status.success() {
        let stderr = String::from_utf8_lossy(&status_output.stderr);
        return Err(anyhow!("git status failed: {}", stderr).into());
    }

    let mut files: Vec<ChangedFile> = Vec::new();

    for line in String::from_utf8_lossy(&status_output.stdout).lines() {
        if line.is_empty() {
            continue;
        }

        // Git status porcelain format: "XY filename"
        // X = index status, Y = working tree status
        let chars: Vec<char> = line.chars().collect();
        if chars.len() < 3 {
            continue;
        }

        let index_status = chars[0];
        let worktree_status = chars[1];
        let file_path = line[3..].trim().to_string();

        // Determine overall status and whether file is untracked
        let is_untracked = index_status == '?' && worktree_status == '?';
        let status = match (index_status, worktree_status) {
            ('M', _) | (_, 'M') => "modified",
            ('A', _) => "added",
            ('?', '?') => "added", // Untracked files are shown as "added"
            ('D', _) | (_, 'D') => "deleted",
            ('R', _) => "renamed",
            _ => "modified",
        }
        .to_string();

        // Get diff stats for this file
        let (additions, deletions) = get_file_diff_stats(source_folder, &file_path, is_untracked);

        files.push(ChangedFile {
            path: file_path,
            status,
            additions,
            deletions,
        });
    }

    Ok(HttpResponse::Ok().json(json!({ "files": files })))
}

/// Helper: Get addition/deletion counts for a single file
/// For untracked files, counts lines in the file as additions
fn get_file_diff_stats(
    source_folder: &std::path::Path,
    file_path: &str,
    is_untracked: bool,
) -> (u32, u32) {
    if is_untracked {
        // For untracked files, count lines as additions
        let file_full_path = source_folder.join(file_path);
        match std::fs::read_to_string(&file_full_path) {
            Ok(content) => {
                let line_count = content.lines().count() as u32;
                (line_count, 0)
            }
            Err(_) => (0, 0),
        }
    } else {
        // For tracked files, use git diff --numstat
        let output = Command::new("git")
            .args(["diff", "--numstat", "HEAD", "--", file_path])
            .current_dir(source_folder)
            .output();

        match output {
            Ok(output) if output.status.success() => {
                let line = String::from_utf8_lossy(&output.stdout);
                let parts: Vec<&str> = line.split_whitespace().collect();
                if parts.len() >= 2 {
                    let additions = parts[0].parse::<u32>().unwrap_or(0);
                    let deletions = parts[1].parse::<u32>().unwrap_or(0);
                    (additions, deletions)
                } else {
                    (0, 0)
                }
            }
            _ => (0, 0),
        }
    }
}

// =============================================================================
// Agent Dialog Endpoints - For real-time conversation monitoring
// =============================================================================

/// Query parameters for /agent/dialog endpoint
#[derive(Deserialize)]
struct DialogQuery {
    /// Only return entries with seq > since (for incremental polling)
    since: Option<i64>,
}

/// GET /agent/dialog - Returns agent dialog entries from JSONL file
///
/// Reads dialog entries from $SSE_ARCHIVE/dialog.jsonl (written by agent wrapper).
/// Supports incremental polling via ?since=seq parameter.
async fn agent_dialog(query: web::Query<DialogQuery>) -> Result<HttpResponse, AppError> {
    debug!(
        "Received request: GET /agent/dialog (since={:?})",
        query.since
    );

    let archive = std::env::var("SSE_ARCHIVE").unwrap_or_else(|_| "/tmp/sse-archive".to_string());
    let dialog_path = std::path::PathBuf::from(archive).join("dialog.jsonl");

    // If file doesn't exist, return empty entries
    if !dialog_path.exists() {
        return Ok(HttpResponse::Ok().json(json!({ "entries": [] })));
    }

    let content = std::fs::read_to_string(dialog_path).context("Failed to read dialog.jsonl")?;

    let since = query.since.unwrap_or(-1);
    let mut entries: Vec<Value> = Vec::new();

    for line in content.lines() {
        if line.trim().is_empty() {
            continue;
        }

        // Parse line as JSON
        match serde_json::from_str::<Value>(line) {
            Ok(entry) => {
                // Check if entry has seq field and filter by since parameter
                if let Some(seq) = entry.get("seq").and_then(|v| v.as_i64()) {
                    if seq > since {
                        entries.push(entry);
                    }
                }
            }
            Err(e) => {
                // Log but skip malformed lines
                log::warn!("Skipping malformed dialog line: {}", e);
            }
        }
    }

    Ok(HttpResponse::Ok().json(json!({ "entries": entries })))
}

// =============================================================================
// Evaluation Result Endpoint - For showing results after agent finishes
// =============================================================================

/// Response structure for evaluation result
#[derive(Serialize)]
struct EvaluationResult {
    available: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    patch_result: Option<PatchResult>,
    #[serde(skip_serializing_if = "Option::is_none")]
    runtime_result: Option<RuntimeResult>,
}

#[derive(Serialize, Deserialize)]
struct PatchResult {
    build_success: Option<bool>,
    pov_passed: Option<i32>,
    pov_total: Option<i32>,
    func_test_success: Option<bool>,
    intent_test_success: Option<bool>,
    error_msg: Option<String>,
    error_log: Option<String>,
}

#[derive(Serialize, Deserialize)]
struct RuntimeResult {
    agent_duration: i32,
    agent_timeout: bool,
    evaluator_timeout: bool,
}

#[derive(Deserialize)]
struct RawEvaluationResult {
    patch_result: PatchResult,
    runtime_result: RuntimeResult,
}

/// GET /result - Returns evaluation result if available
///
/// Reads the evaluation result from /sse_result (written by evaluator after agent finishes).
/// Returns { available: false } if result file doesn't exist or is empty.
async fn result() -> Result<HttpResponse, AppError> {
    debug!("Received request: GET /result");

    let result_path = std::path::Path::new("/sse_result");

    // Check if result file exists and is non-empty
    if !result_path.exists() {
        return Ok(HttpResponse::Ok().json(EvaluationResult {
            available: false,
            patch_result: None,
            runtime_result: None,
        }));
    }

    let content = std::fs::read_to_string(result_path).context("Failed to read result file")?;

    if content.trim().is_empty() {
        return Ok(HttpResponse::Ok().json(EvaluationResult {
            available: false,
            patch_result: None,
            runtime_result: None,
        }));
    }

    // Parse the result JSON
    match serde_json::from_str::<RawEvaluationResult>(&content) {
        Ok(raw) => Ok(HttpResponse::Ok().json(EvaluationResult {
            available: true,
            patch_result: Some(raw.patch_result),
            runtime_result: Some(raw.runtime_result),
        })),
        Err(e) => {
            log::warn!("Failed to parse result JSON: {}", e);
            Ok(HttpResponse::Ok().json(EvaluationResult {
                available: false,
                patch_result: None,
                runtime_result: None,
            }))
        }
    }
}

// =============================================================================
// Grading Endpoints - For evaluator use (not for agents!)
// =============================================================================

/// Helper: resolve the archive directory from $SSE_ARCHIVE (default: /tmp/sse-archive).
fn archive_dir() -> std::path::PathBuf {
    std::path::PathBuf::from(
        std::env::var("SSE_ARCHIVE").unwrap_or_else(|_| "/tmp/sse-archive".to_string()),
    )
}

/// POST /prepare_grading - Clean the source folder for grading
///
/// Captures the agent's diff and commit messages, resets the repo to the
/// original buggy commit, removes all untracked/gitignored files, and
/// re-applies only the agent's meaningful code changes.
///
/// The captured diff is saved to $SSE_ARCHIVE/final.patch and can be
/// retrieved later via GET /final_diff.
///
/// IMPORTANT: This is an intrusive, destructive operation. It should only
/// be called by the evaluator after the agent has finished working, and so is
/// restricted to the privileged admin socket.
async fn prepare_grading_handler(
    state: web::Data<AppState>,
    access: web::Data<Access>,
) -> Result<HttpResponse, AppError> {
    debug!("Received request: POST /prepare_grading");

    if !access.privileged {
        return Ok(forbidden_privileged());
    }

    let source_folder = state.project.source_folder();
    let archive = archive_dir();

    prepare_grading(source_folder, &archive)?;

    Ok(HttpResponse::Ok().json(json!({ "success": true })))
}

/// GET /final_diff - Returns the agent's final diff captured during prepare_grading
///
/// Reads the saved diff from $SSE_ARCHIVE/final.patch (written by POST /prepare_grading).
/// Returns { "diff": "" } if prepare_grading has not been called yet.
async fn final_diff() -> Result<HttpResponse, AppError> {
    debug!("Received request: GET /final_diff");

    let patch_path = archive_dir().join("final.patch");

    if !patch_path.exists() {
        return Ok(HttpResponse::Ok().json(json!({ "diff": "" })));
    }

    let content = std::fs::read_to_string(&patch_path).context("Failed to read final.patch")?;

    Ok(HttpResponse::Ok().json(json!({ "diff": content })))
}

// =============================================================================
// Reference Patch & Phase Endpoints - privileged / post-agent only
// =============================================================================

/// Build the standard 403 body for a request that reached a privileged-only
/// route on an agent-facing listener.
fn forbidden_privileged() -> HttpResponse {
    HttpResponse::Forbidden().json(json!({
        "error": "endpoint is only available on the admin socket"
    }))
}

/// GET /reference/patch - Returns the reference (ground truth) patch.
///
/// This is the answer to the task and must never reach the agent while it
/// works. It is served in two cases only:
///   - on the privileged admin socket (used by post-agent tooling), or
///   - on an agent-facing listener *after* the agent phase has ended, so the
///     web UI can fetch it from the host once the run is over.
///
/// Returns the same format as /diff: { "diff": "..." }
async fn reference_patch(
    state: web::Data<AppState>,
    access: web::Data<Access>,
) -> Result<HttpResponse, AppError> {
    debug!("Received request: GET /reference/patch");

    if !access.privileged && !state.agent_phase_ended() {
        return Ok(HttpResponse::Forbidden().json(json!({
            "error": "reference patch is unavailable while the agent is running"
        })));
    }

    let patch_path = match state.project.ground_truth_patch_file() {
        Some(path) => path,
        None => {
            return Ok(HttpResponse::Ok().json(json!({ "diff": "" })));
        }
    };

    match std::fs::read_to_string(patch_path) {
        Ok(content) => Ok(HttpResponse::Ok().json(json!({ "diff": content }))),
        Err(e) => {
            log::warn!("Failed to read reference patch at {:?}: {}", patch_path, e);
            Ok(HttpResponse::Ok().json(json!({ "diff": "" })))
        }
    }
}

/// POST /admin/agent_exited - Mark the agent phase as ended.
///
/// The entrypoint calls this over the admin socket once the agent process
/// exits, which unlocks the reference patch on the agent-facing listeners for
/// the web UI. Privileged-only.
async fn agent_exited(
    state: web::Data<AppState>,
    access: web::Data<Access>,
) -> Result<HttpResponse, AppError> {
    debug!("Received request: POST /admin/agent_exited");

    if !access.privileged {
        return Ok(forbidden_privileged());
    }

    state.end_agent_phase();
    Ok(HttpResponse::Ok().json(json!({ "success": true })))
}

/// Declares every route once: `configure_routes` registers them and `ROUTES`
/// lists them, so the OpenAPI contract test sees exactly what is served.
macro_rules! routes {
    ($($method:ident $path:literal => $handler:ident,)*) => {
        /// Every route as (lowercase HTTP method, path template), in the order
        /// they are registered. `openapi.yaml` must describe exactly these.
        pub const ROUTES: &[(&str, &str)] = &[$((stringify!($method), $path),)*];

        /// Configure all routes for the application.
        pub fn configure_routes(cfg: &mut web::ServiceConfig) {
            $(cfg.route($path, web::$method().to($handler));)*
        }
    };
}

routes! {
    get "/version" => version,
    get "/project" => project,
    get "/capabilities" => capabilities,
    post "/tool/{name}" => tool,
    // WebUI endpoints for code change monitoring
    get "/diff" => diff,
    get "/files" => files,
    // Agent dialog endpoint
    get "/agent/dialog" => agent_dialog,
    // Evaluation result endpoint
    get "/result" => result,
    // Grading: only the admin socket prepares it; the diff it saved is readable on every listener
    post "/prepare_grading" => prepare_grading_handler,
    get "/final_diff" => final_diff,
    // Phase control (privileged admin socket only)
    post "/admin/agent_exited" => agent_exited,
    // Reference patch: privileged, or agent-facing only after the agent phase
    get "/reference/patch" => reference_patch,
}
