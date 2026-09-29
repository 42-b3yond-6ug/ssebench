use std::path::Path;
use std::process::Command;

use anyhow::Result;

use super::logging::log_script;
use crate::isolation::run_captured;

/// Output from running a script
#[derive(Debug, Clone, PartialEq)]
pub struct ScriptOutput {
    pub code: i32,
    pub stdout: String,
    pub stderr: String,
}

impl ScriptOutput {
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

/// Execute a script or command with arguments in the specified working
/// directory, as the daemon's own user. Task scripts go through
/// [`crate::isolation::TaskRunner`] instead.
pub fn run_script<P: AsRef<Path>>(binary: &str, args: &[String], cwd: P) -> Result<ScriptOutput> {
    let mut cmd = Command::new(binary);
    cmd.current_dir(cwd).args(args);
    let description = format!("{cmd:?}");
    let output = run_captured(cmd, None)?;
    log_script(&description, &output);
    Ok(output)
}
