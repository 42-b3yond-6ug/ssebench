use std::io::{BufRead, BufReader, Write};
use std::os::unix::process::CommandExt;
use std::path::Path;
use std::process::Stdio;
use std::sync::mpsc;
use std::sync::{Arc, Mutex};
use std::thread;

use anyhow::{Result, anyhow};
use serde::Deserialize;

use crate::isolation::{TrackedGroup, agent_account};

use super::Tool;
use super::response::{ScriptResult, ToolResult};
use super::{ToolRequest, ToolResponse, parse_and_run};

/// Tool-specific result alias
pub type BashResult = ScriptResult;

/// Output from the bash shell
#[derive(Debug, Clone)]
pub enum ShellOutput {
    Stdout(String),
    Stderr(String),
    Closed,
}

/// Interactive bash shell tool.
#[derive(Debug, Clone)]
pub struct Bash {
    speaker: Arc<Mutex<mpsc::Sender<String>>>,
    listener: Arc<Mutex<mpsc::Receiver<ShellOutput>>>,
}

const EXIT_MARKER_PREFIX: &str = "___SSE_EXIT___";
const EXIT_MARKER_SUFFIX: &str = "___";

#[derive(Debug, Deserialize)]
struct Argument {
    command: String,
}

impl Tool for Bash {
    fn name(&self) -> String {
        "bash".into()
    }

    fn description(&self) -> String {
        "A bash session started at the source folder".into()
    }

    fn handle(&mut self, request: ToolRequest) -> ToolResponse {
        parse_and_run::<Argument, _>(&request, |argument| {
            self.execute(&argument.command)
                .map(ToolResult::Script)
                .map_err(|e| anyhow!("{}", e))
        })
    }
}

impl Bash {
    pub fn new<P: AsRef<Path>>(working_directory: P) -> Result<Self> {
        let working_dir = working_directory.as_ref().to_path_buf();

        // Spawn bash process synchronously to properly propagate errors
        let mut child = agent_account()
            .command("bash")
            .current_dir(&working_dir)
            .arg("-i")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .process_group(0)
            .spawn()?;
        let group = TrackedGroup::new(child.id());

        let mut stdin = child
            .stdin
            .take()
            .ok_or_else(|| anyhow!("failed to capture stdin"))?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| anyhow!("failed to capture stdout"))?;
        let stderr = child
            .stderr
            .take()
            .ok_or_else(|| anyhow!("failed to capture stderr"))?;

        let (input_tx, input_rx) = mpsc::channel();
        let (output_tx, output_rx) = mpsc::channel();

        // Spawn management thread for I/O handling
        thread::spawn(move || {
            let stdin_rx = input_rx;
            let stdout_tx = output_tx.clone();
            let stdin_tx = output_tx.clone();

            let first = Arc::new(Mutex::new(true));
            let stdin_first = first.clone();
            let stderr_first = first.clone();

            let stdin_listener = thread::spawn(move || {
                while let Ok(command) = stdin_rx.recv() {
                    let mut f = stdin_first.lock().unwrap();
                    *f = true;
                    if write!(stdin, "{}", command).is_err() {
                        let _ = stdin_tx.send(ShellOutput::Closed);
                        break;
                    }
                }
            });

            let stdout_listener = thread::spawn(move || {
                let mut reader = BufReader::new(stdout);
                let mut line = String::new();
                while let Ok(bytes) = reader.read_line(&mut line) {
                    if bytes == 0 {
                        break;
                    }
                    if stdout_tx.send(ShellOutput::Stdout(line.clone())).is_err() {
                        break;
                    }
                    line.clear();
                }
                let _ = stdout_tx.send(ShellOutput::Closed);
            });

            let stderr_listener = thread::spawn(move || {
                let mut reader = BufReader::new(stderr);
                let mut line = String::new();
                while let Ok(bytes) = reader.read_line(&mut line) {
                    let mut f = stderr_first.lock().unwrap();
                    if *f {
                        // don't write first line because it's the prompt
                        *f = false;
                        line.clear();
                        continue;
                    }

                    if bytes == 0 {
                        break;
                    }
                    if output_tx.send(ShellOutput::Stderr(line.clone())).is_err() {
                        break;
                    }
                    line.clear();
                }
                let _ = output_tx.send(ShellOutput::Closed);
            });

            let _ = stdin_listener.join();
            let _ = stdout_listener.join();
            let _ = stderr_listener.join();
            let _ = child.wait();
            drop(group);
        });

        Ok(Self {
            speaker: Arc::new(Mutex::new(input_tx)),
            listener: Arc::new(Mutex::new(output_rx)),
        })
    }

    /// Execute a command and wait for completion.
    fn execute_command(&mut self, command: &str) -> Result<BashResult> {
        let speaker = self.speaker.lock().unwrap();
        let listener = self.listener.lock().unwrap();

        speaker
            .send(command.to_string())
            .map_err(|_| anyhow!("bash process has died"))?;

        let mut exit_code = 0;
        let mut stdout_buffer = String::new();
        let mut stderr_buffer = String::new();

        while let Ok(event) = listener.recv() {
            match event {
                ShellOutput::Stdout(line) => {
                    let trimmed = line.trim();
                    if let Some(rest) = trimmed.strip_prefix(EXIT_MARKER_PREFIX) {
                        if let Some(code_str) = rest.strip_suffix(EXIT_MARKER_SUFFIX) {
                            if let Ok(code) = code_str.parse::<i32>() {
                                exit_code = code;
                            }
                        }
                        break;
                    }
                    stdout_buffer.push_str(&line);
                }
                ShellOutput::Stderr(line) => {
                    stderr_buffer.push_str(&line);
                }
                ShellOutput::Closed => {
                    return Ok(BashResult::new(exit_code, stdout_buffer, stderr_buffer));
                }
            }
        }

        Ok(BashResult::new(exit_code, stdout_buffer, stderr_buffer))
    }

    /// Execute a command synchronously (blocking).
    ///
    /// # Security Note
    /// Commands run in the current shell context, so environment changes (cd, export, etc.)
    /// persist across invocations. The `exit` command will terminate the bash session.
    /// Command injection is possible but acceptable because the bash process runs as the agent's user
    /// (a regular, unprivileged user) which limits potential damage.
    fn execute(&mut self, command: &str) -> Result<BashResult> {
        let command_string = format!(
            "{{ {}; }}; echo \"{}{}{}\"\n",
            command, EXIT_MARKER_PREFIX, "$?", EXIT_MARKER_SUFFIX
        );
        self.execute_command(&command_string)
    }
}
