use std::path::PathBuf;

use serde::{Deserialize, Serialize};

/// Public view of task description with crash report contents instead of paths.
#[derive(Clone, Debug, Serialize)]
pub struct PublicTaskDescription {
    pub issue: Option<String>,
    /// Crash report file contents (read from disk by the daemon).
    pub crash_report: Option<Vec<String>>,
    pub bug_description: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct TaskDescription {
    #[serde(default)]
    pub issue: Option<String>,
    #[serde(default, rename = "crash_report")]
    pub crash_report: Option<Vec<PathBuf>>,
    #[serde(default)]
    pub bug_description: Option<String>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct Files {
    #[serde(default)]
    pub patch: Option<PathBuf>,
    #[serde(default, rename = "future_test")]
    pub intent_test: Option<PathBuf>,
    #[serde(default)]
    pub poc: Vec<PathBuf>,
}

/// Script paths for build, run (PoC execution), and test operations.
#[derive(Clone, Debug, Deserialize)]
pub struct Scripts {
    #[serde(default)]
    pub build: Option<PathBuf>,
    #[serde(default)]
    pub run: Option<PathBuf>,
    #[serde(default)]
    pub test: Option<PathBuf>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct Metadata {
    pub id: String,
    pub project: String,

    // Operational Fields
    pub language: String,
    pub source: PathBuf,
    pub task_description: TaskDescription,
    pub scripts: Scripts,
    pub files: Files,

    // Informative Fields
    #[serde(default)]
    pub sanitizer: Option<String>,
    #[serde(default, rename = "type")]
    pub bug_type: Option<String>,
    #[serde(default)]
    pub binary: Option<String>,
    #[serde(default)]
    pub trigger_commit: Option<String>,
    #[serde(default)]
    pub patch_commit: Option<String>,
    #[serde(default)]
    pub reference: Option<Vec<String>>,
}

#[derive(Serialize)]
pub struct PublicMetadata {
    pub id: String,
    pub project: String,
    pub language: String,
    pub source: PathBuf,
    pub task_description: PublicTaskDescription,
    pub poc: Vec<PathBuf>,
    pub build_script: Option<String>,
    pub test_script: Option<String>,
}

pub fn load_metadata(yaml_content: &str) -> Result<Metadata, serde_yaml::Error> {
    serde_yaml::from_str(yaml_content)
}
