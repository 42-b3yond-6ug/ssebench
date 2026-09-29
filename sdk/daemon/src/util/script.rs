use std::io::Write;
use std::path::Path;
use std::process::Command;

use anyhow::Result;

use super::logging::create_timestamped_log;

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

/// Execute a script or command with arguments in the specified working directory.
pub fn run_script<P: AsRef<Path>>(binary: &str, args: &[String], cwd: P) -> Result<ScriptOutput> {
    let mut cmd = Command::new(binary);
    cmd.current_dir(cwd);
    cmd.args(args);

    let output = cmd.output()?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    let code = output.status.code().unwrap_or(-1);

    if let Ok(mut f) = create_timestamped_log("scriptrunner") {
        writeln!(f, "{:?}", cmd).ok();
        writeln!(f, "code={}", code).ok();
        writeln!(f, "=== stdout ===\n{}", stdout).ok();
        writeln!(f, "=== stderr ===\n{}", stderr).ok();
    }

    Ok(ScriptOutput::new(
        code,
        stdout.to_string(),
        stderr.to_string(),
    ))
}
