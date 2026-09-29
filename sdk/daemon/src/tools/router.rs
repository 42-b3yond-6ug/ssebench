use std::collections::HashMap;
use std::sync::Arc;

use anyhow::anyhow;
use serde_json::Value;

use crate::bench::BenchCore;
use crate::isolation::TaskRunner;

use super::Tool;
use super::bash::Bash;
use super::bencher::Bencher;
use super::{ToolRequest, ToolResponse};

/// Routes tool requests to the appropriate tool handler.
pub struct ToolRouter {
    tools: HashMap<String, Box<dyn Tool>>,
    bencher: Bencher,
}

impl ToolRouter {
    /// Create a new router with tools initialized from current bench. The
    /// bencher runs the task's scripts through `runner`.
    pub fn new(bench: Arc<BenchCore>, runner: TaskRunner) -> Self {
        let mut tools: HashMap<String, Box<dyn Tool>> = HashMap::new();
        if let Ok(bash) = Bash::new(bench.source_folder()) {
            tools.insert(bash.name(), Box::new(bash));
        }
        Self {
            tools,
            bencher: Bencher::new(bench, runner),
        }
    }

    /// Start grading with a fresh runner session; see [`Bencher::start_grading`].
    pub fn start_grading(&mut self) -> anyhow::Result<()> {
        self.bencher.start_grading()
    }

    /// Route a request to the appropriate tool and return the encoded result.
    pub fn route(&mut self, name: &str, action: &str, arg: &Value) -> ToolResponse {
        println!("Tool call name={} action={} arg={:?}", name, action, arg);

        let request = ToolRequest {
            action: action.into(),
            argument: arg.clone(),
        };
        if name == self.bencher.name() {
            return self.bencher.handle(request);
        }
        let tool = self
            .tools
            .get_mut(name)
            .ok_or_else(|| anyhow!("tool not found: {}", name))?;

        tool.handle(request)
    }

    /// Get list of available tool names.
    pub fn available_tools(&self) -> Vec<String> {
        let mut names: Vec<String> = self.tools.keys().cloned().collect();
        names.push(self.bencher.name());
        names
    }
}
