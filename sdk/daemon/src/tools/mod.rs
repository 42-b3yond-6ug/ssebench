mod bash;
mod bencher;
mod response;
mod router;

use anyhow::{Result, anyhow};
use serde::Deserialize;
use serde::de::DeserializeOwned;
use serde_json::Value;

pub use bash::{Bash, BashResult};
pub use bencher::{Bencher, BencherResult};
pub use response::{ScriptResult, ToolResult};
pub use router::ToolRouter;

/// Trait for tools that can handle requests.
pub trait Tool: Send + Sync + std::fmt::Debug {
    /// Get the name of this tool.
    fn name(&self) -> String;

    /// Get the description of this tool.
    fn description(&self) -> String;

    /// Handle a tool request and return the result.
    fn handle(&mut self, request: ToolRequest) -> ToolResponse;
}

/// Request sent to a tool.
#[derive(Debug, Clone, Deserialize)]
pub struct ToolRequest {
    pub action: String,
    pub argument: Value,
}

/// Response type for tool invocations.
pub type ToolResponse = Result<ToolResult>;

/// Parse request argument and run handler.
pub fn parse_and_run<T, F>(req: &ToolRequest, handler: F) -> ToolResponse
where
    T: DeserializeOwned,
    F: FnOnce(T) -> ToolResponse,
{
    serde_json::from_value::<T>(req.argument.clone())
        .map_err(|e| anyhow!("invalid argument: {}", e))
        .and_then(handler)
}

#[cfg(test)]
mod tests;
