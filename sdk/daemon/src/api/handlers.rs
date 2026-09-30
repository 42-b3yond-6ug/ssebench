use std::sync::Arc;

use actix_web::{HttpResponse, web};
use anyhow::{Context, anyhow};
use log::debug;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use super::diff::baseline;
use super::error::AppError;
use super::grading::prepare_grading;
use super::state::{Access, AppState};
use crate::isolation::{agent_account, is_root, kill_all_processes_of};
use crate::util::{archive_dir, results_dir};

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
///
/// The agent-facing listeners serve tools only during the agent phase, and
/// never run a check on the grading copy of the project.
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

    if !access.privileged && state.agent_phase_ended() {
        return Ok(HttpResponse::Forbidden().json(json!({
            "error": "tools are unavailable after the agent phase"
        })));
    }
    if !access.privileged && arg.get("grading").and_then(Value::as_bool) == Some(true) {
        return Ok(HttpResponse::Forbidden().json(json!({
            "error": "grading checks are only available on the admin socket"
        })));
    }
    if !access.privileged && name == "bencher" && !state.difficulty.allows_bencher_action(&action) {
        return Ok(HttpResponse::Forbidden().json(json!({
            "error": format!(
                "action '{}' is not available at the current difficulty level",
                action
            )
        })));
    }

    // The lock and the command run on the blocking pool: a worker that waits
    // for either would not answer the read-only routes.
    let router = Arc::clone(&state.tool_router);
    web::block(move || router.lock().unwrap().route(&name, &action, &arg))
        .await
        .map_err(|e| anyhow!("the tool call did not finish: {e}"))?
        .map(|result| HttpResponse::Ok().json(result))
        .map_err(AppError::from)
}

// =============================================================================
// WebUI Endpoints - For real-time code change monitoring
// =============================================================================

/// GET /diff - Returns the agent's changes so far: the working tree against the
/// task's base commit, captured as for grading (see `diff::Baseline`).
async fn diff() -> Result<HttpResponse, AppError> {
    debug!("Received request: GET /diff");

    let diff_text = baseline()?.diff()?;

    Ok(HttpResponse::Ok().json(json!({
        "diff": String::from_utf8_lossy(&diff_text)
    })))
}

/// GET /files - Returns the files in `GET /diff`, each with its status
/// (added, deleted or modified) and line counts.
async fn files() -> Result<HttpResponse, AppError> {
    debug!("Received request: GET /files");

    let files = baseline()?.changed_files()?;

    Ok(HttpResponse::Ok().json(json!({ "files": files })))
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

    let dialog_path = archive_dir().join("dialog.jsonl");

    // No file (or not a plain file) means no entries yet.
    let Some(content) = read_agent_file(&dialog_path).context("Failed to read dialog.jsonl")?
    else {
        return Ok(HttpResponse::Ok().json(json!({ "entries": [] })));
    };

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
    /// `passed`, `failed`, or `error` when the patch was not graded.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    status: Option<String>,
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

/// Read a file in a directory the agent can write, without following a
/// link the agent may have put there. `None` if it is missing or not a
/// regular file.
fn read_agent_file(path: &std::path::Path) -> std::io::Result<Option<String>> {
    use std::io::Read;
    use std::os::unix::fs::OpenOptionsExt;

    let file = std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path);
    let mut file = match file {
        Ok(file) => file,
        Err(e)
            if e.kind() == std::io::ErrorKind::NotFound
                || e.raw_os_error() == Some(libc::ELOOP) =>
        {
            return Ok(None);
        }
        Err(e) => return Err(e),
    };
    if !file.metadata()?.is_file() {
        return Ok(None);
    }
    let mut content = Vec::new();
    file.read_to_end(&mut content)?;
    Ok(Some(String::from_utf8_lossy(&content).into_owned()))
}

/// The grade the evaluator wrote: `result.json` in the results directory, or
/// `/sse_result` for a container without one.
fn result_file() -> std::path::PathBuf {
    if std::env::var_os("SSE_RESULTS").is_some() {
        results_dir().join("result.json")
    } else {
        std::path::PathBuf::from("/sse_result")
    }
}

/// GET /result - Returns evaluation result if available
///
/// Reads the evaluation result the evaluator wrote after the agent finished.
/// Returns { available: false } if result file doesn't exist or is empty.
async fn result() -> Result<HttpResponse, AppError> {
    debug!("Received request: GET /result");

    let result_path = result_file();

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

/// POST /prepare_grading - Prepare the grading copy of the project
///
/// Starts a fresh task-runner session for grading, captures the agent's diff
/// and commit messages, and applies the diff to the clean copy of the project
/// that grading builds and tests.
///
/// The captured diff is saved to final.patch in the results directory and
/// can be retrieved later via GET /final_diff.
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

    // Waits for a running tool call, so it does not hold a worker.
    let router = Arc::clone(&state.tool_router);
    web::block(move || router.lock().unwrap().start_grading())
        .await
        .map_err(|e| anyhow!("starting the grading session did not finish: {e}"))??;
    prepare_grading(baseline()?, &results_dir())?;

    Ok(HttpResponse::Ok().json(json!({ "success": true })))
}

/// GET /final_diff - Returns the agent's final diff captured during prepare_grading
///
/// Reads the saved diff from $SSE_ARCHIVE/final.patch (written by POST /prepare_grading).
/// Returns { "diff": "" } if prepare_grading has not been called yet.
async fn final_diff() -> Result<HttpResponse, AppError> {
    debug!("Received request: GET /final_diff");

    let patch_path = results_dir().join("final.patch");

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
/// This is the answer to the task. Only the privileged admin socket serves
/// it, at any time: the agent-facing listeners reach other containers on the
/// run network too, including after the run when a container is kept.
/// Post-run tooling on the host reads the task folder or the run's results.
///
/// Returns the same format as /diff: { "diff": "..." }
async fn reference_patch(
    state: web::Data<AppState>,
    access: web::Data<Access>,
) -> Result<HttpResponse, AppError> {
    debug!("Received request: GET /reference/patch");

    if !access.privileged {
        return Ok(forbidden_privileged());
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
/// exits. From then on the agent-facing listeners refuse tools, and every
/// process of the agent's user in this container is killed: what the agent
/// left running (through the bash tool, or detached from its session) must
/// not run next to grading. Privileged-only.
async fn agent_exited(
    state: web::Data<AppState>,
    access: web::Data<Access>,
) -> Result<HttpResponse, AppError> {
    debug!("Received request: POST /admin/agent_exited");

    if !access.privileged {
        return Ok(forbidden_privileged());
    }

    state.end_agent_phase();
    if is_root() {
        kill_all_processes_of(agent_account()).context("failed to stop the agent's processes")?;
    }
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
    // Reference patch (privileged admin socket only)
    get "/reference/patch" => reference_patch,
}

#[cfg(test)]
mod result_tests {
    use super::RawEvaluationResult;

    #[test]
    fn result_keeps_the_grade_status() {
        let raw: RawEvaluationResult = serde_json::from_str(
            r#"{"patch_result": {"status": "error", "error_msg": "Timeout (60s)"},
                "runtime_result": {"agent_duration": 3, "agent_timeout": false, "evaluator_timeout": true}}"#,
        )
        .unwrap();
        let patch = serde_json::to_value(&raw.patch_result).unwrap();
        assert_eq!(patch["status"], "error");
        assert_eq!(patch["error_msg"], "Timeout (60s)");
    }

    #[test]
    fn result_without_a_status_is_still_served() {
        let raw: RawEvaluationResult = serde_json::from_str(
            r#"{"patch_result": {"build_success": true},
                "runtime_result": {"agent_duration": 3, "agent_timeout": false, "evaluator_timeout": false}}"#,
        )
        .unwrap();
        let patch = serde_json::to_value(&raw.patch_result).unwrap();
        assert!(patch.get("status").is_none());
        assert_eq!(patch["build_success"], true);
    }
}
