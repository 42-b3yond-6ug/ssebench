use serde::Serialize;

/// Result type for script execution - shared across tools.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct ScriptResult {
    pub code: i32,
    pub stdout: String,
    pub stderr: String,
}

impl ScriptResult {
    pub fn new(code: i32, stdout: String, stderr: String) -> Self {
        Self {
            code,
            stdout,
            stderr,
        }
    }

    pub fn success(&self) -> bool {
        self.code == 0
    }
}

impl From<crate::util::ScriptOutput> for ScriptResult {
    fn from(output: crate::util::ScriptOutput) -> Self {
        Self {
            code: output.code,
            stdout: output.stdout,
            stderr: output.stderr,
        }
    }
}

/// Result of a tool invocation, encoded for response.
#[derive(Serialize)]
#[serde(untagged)]
pub enum ToolResult {
    Script(ScriptResult),
    Empty,
}

impl ToolResult {
    pub fn from_script(result: ScriptResult) -> Self {
        Self::Script(result)
    }

    pub fn empty() -> Self {
        Self::Empty
    }
}
