use std::collections::HashMap;
use std::sync::Arc;

use anyhow::anyhow;
use serde_json::Value;

use crate::bench::BenchCore;

use super::Tool;
use super::bash::Bash;
use super::bencher::Bencher;
use super::{ToolRequest, ToolResponse};

/// Routes tool requests to the appropriate tool handler.
pub struct ToolRouter {
    tools: HashMap<String, Box<dyn Tool>>,
}

impl ToolRouter {
    /// Create a new router with tools initialized from current bench.
    pub fn new(bench: Arc<BenchCore>) -> Self {
        let mut router = Self {
            tools: HashMap::new(),
        };
        router.register_tools(bench);
        router
    }

    fn register_tools(&mut self, bench: Arc<BenchCore>) {
        // Register bash tool
        if let Ok(bash) = Bash::new(bench.source_folder()) {
            self.tools.insert(bash.name(), Box::new(bash));
        }

        // Register bencher tool
        let bencher = Bencher::new(bench);
        self.tools.insert(bencher.name(), Box::new(bencher));
    }

    /// Route a request to the appropriate tool and return the encoded result.
    pub fn route(&mut self, name: &str, action: &str, arg: &Value) -> ToolResponse {
        println!("Tool call name={} action={} arg={:?}", name, action, arg);

        let tool = self
            .tools
            .get_mut(name)
            .ok_or_else(|| anyhow!("tool not found: {}", name))?;

        tool.handle(ToolRequest {
            action: action.into(),
            argument: arg.clone(),
        })
    }

    /// Get list of available tool names.
    pub fn available_tools(&self) -> Vec<&str> {
        self.tools.keys().map(|s| s.as_str()).collect()
    }
}
