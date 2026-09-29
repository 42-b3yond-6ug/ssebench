use std::sync::{Arc, Mutex};

use crate::bench::BenchCore;
use crate::tools::ToolRouter;

/// Application state made available to all request handlers. Actix clones this struct once per
/// worker thread, so only fields wrapped in `Arc` are truly shared across the entire application.
/// Other fields would be independently cloned per worker.
///
/// # Note
///
/// ToolRouter is guarded by a Mutex because the daemon’s tool workflow is logically
/// stateful and must run sequentially. Although the API surface looks stateless, tools operate on
/// shared internal state (e.g., a temporary working directory).
///
/// Certain tool sequences, such as `build` followed by `test`, must run on the same underlying
/// state, which requires `&mut self` access inside ToolRouter. Since multiple Actix workers may
/// attempt to invoke tools concurrently, we wrap ToolRouter in `Arc<Mutex<_>>` to ensure
/// exclusive, serialized access to this stateful workflow.
///
/// If we ever support true multi‑agent workflows, this Mutex will need to be replaced with a
/// session‑scoped mechanism (e.g., a per‑agent session token managed by the SDK). Each agent would
/// require isolated tool state rather than contending for a single global ToolRouter lock.
///
/// How multi‑agent isolation should interact with the MCP server model is still an open design
/// question. This is a future exploration topic and not a near‑term requirement.
pub struct AppState {
    pub project: Arc<BenchCore>,
    pub tool_router: Arc<Mutex<ToolRouter>>,
}

impl AppState {
    pub fn new(project: BenchCore) -> Self {
        let project = Arc::new(project);
        let router = ToolRouter::new(Arc::clone(&project));
        Self {
            project,
            tool_router: Arc::new(Mutex::new(router)),
        }
    }
}

impl Clone for AppState {
    fn clone(&self) -> Self {
        Self {
            project: Arc::clone(&self.project),
            tool_router: Arc::clone(&self.tool_router),
        }
    }
}
