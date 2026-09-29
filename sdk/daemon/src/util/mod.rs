mod fs;
mod logging;
pub mod script;

pub use fs::copy_folder_to_temp;
pub use logging::create_timestamped_log;
pub use script::{ScriptOutput, run_script};

/// Return the path to the pre-populated clean clone of the original repo.
///
/// Reads `SSE_REPO_PATH` from the environment; defaults to `/ssebench-repo`.
/// The agent's patch is applied here during grading so that the live source
/// folder is never destructively cleaned.
pub fn ssebench_repo_path() -> std::path::PathBuf {
    std::path::PathBuf::from(
        std::env::var("SSE_REPO_PATH").unwrap_or_else(|_| "/ssebench-repo".to_string()),
    )
}
