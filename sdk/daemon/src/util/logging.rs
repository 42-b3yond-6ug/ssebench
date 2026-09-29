use std::env;
use std::fs::{self, File};
use std::io::Write;
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

use super::ScriptOutput;

const DEFAULT_ARCHIVE: &str = "/tmp/sse-archive";

/// The run's root-only results directory: `SSE_RESULTS`, where the daemon
/// writes its logs and the patch it captured for grading. Without it (a
/// daemon started by something other than the entrypoint), `SSE_ARCHIVE`.
pub fn results_dir() -> PathBuf {
    env::var_os("SSE_RESULTS")
        .or_else(|| env::var_os("SSE_ARCHIVE"))
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(DEFAULT_ARCHIVE))
}

/// The agent's archive directory, `SSE_ARCHIVE`, where it writes its dialog.
pub fn archive_dir() -> PathBuf {
    env::var_os("SSE_ARCHIVE")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from(DEFAULT_ARCHIVE))
}

/// Create a timestamped log file with the given tag in the results directory.
pub fn create_timestamped_log(tag: &str) -> std::io::Result<File> {
    let dir_path = results_dir();
    fs::create_dir_all(&dir_path)?;

    let filename = match SystemTime::now().duration_since(UNIX_EPOCH) {
        Ok(now) => format!("{}-{}.log", tag, now.as_millis()),
        Err(_) => format!("{}.log", tag),
    };
    File::create(dir_path.join(filename))
}

/// Log one script run as `scriptrunner-<ms>.log`.
pub fn log_script(command: &str, output: &ScriptOutput) {
    if let Ok(mut f) = create_timestamped_log("scriptrunner") {
        writeln!(f, "{}", command).ok();
        writeln!(f, "code={}", output.code).ok();
        writeln!(f, "=== stdout ===\n{}", output.stdout).ok();
        writeln!(f, "=== stderr ===\n{}", output.stderr).ok();
    }
}
