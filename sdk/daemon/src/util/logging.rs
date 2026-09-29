use std::env;
use std::fs::{self, File};
use std::path::PathBuf;
use std::time::{SystemTime, UNIX_EPOCH};

const ENV_LOG_FOLDER: &str = "SSE_ARCHIVE";
const DEFAULT_LOG_FOLDER: &str = "/tmp/sse-archive";

/// Create a timestamped log file with the given tag.
pub fn create_timestamped_log(tag: &str) -> std::io::Result<File> {
    let dir_path =
        PathBuf::from(env::var(ENV_LOG_FOLDER).unwrap_or_else(|_| DEFAULT_LOG_FOLDER.to_string()));

    fs::create_dir_all(&dir_path)?;

    let start = SystemTime::now();
    if let Ok(current_time) = start.duration_since(UNIX_EPOCH) {
        let filename = format!("{}-{}.log", tag, current_time.as_millis());
        File::create(dir_path.join(filename))
    } else {
        let filename = format!("{}.log", tag);
        File::create(dir_path.join(filename))
    }
}
