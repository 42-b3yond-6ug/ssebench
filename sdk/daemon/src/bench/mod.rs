pub mod metadata;

use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Result, anyhow, bail};
use serde::Serialize;

pub use metadata::{Metadata, PublicMetadata, PublicTaskDescription, Scripts, load_metadata};

/// Describes which operations are available for the current benchmark case.
#[derive(Debug, Clone, Serialize)]
pub struct Capabilities {
    pub can_build: bool,
    pub can_run_poc: bool,
    pub poc_count: usize,
    pub has_function_test: bool,
    pub has_intent_test: bool,
}

#[derive(Debug, Clone)]
pub struct BenchCore {
    metadata: Metadata,
    source_folder: PathBuf,
    /// Resolved (absolute) script paths for build, run, and test operations
    scripts: Scripts,
    /// Resolved absolute paths to crash report files (if configured)
    crash_report_files: Option<Vec<PathBuf>>,
    /// Resolved absolute path to the intent test patch (if configured)
    intent_test_file: Option<PathBuf>,
    /// Resolved absolute path to the ground truth patch (if configured)
    ground_truth_patch_file: Option<PathBuf>,
}

impl BenchCore {
    /// Create a new ProjectCore from a SSEBench folder.
    pub fn new(ssebench_folder: impl AsRef<Path>) -> Result<Self> {
        let project_path = ssebench_folder.as_ref();
        let metadata_file = project_path.join("config.yaml");

        // Check project directory
        if !project_path.exists() || !project_path.is_dir() {
            bail!("project directory not found: {}", project_path.display());
        }

        // Check metadata file
        if !metadata_file.exists() || !metadata_file.is_file() {
            bail!("metadata file not found: {}", metadata_file.display());
        }

        // Load metadata
        let mut metadata = load_metadata_from_file(&metadata_file)?;

        // Validate PoCs
        metadata.files.poc = metadata
            .files
            .poc
            .iter()
            .map(|p| {
                let f = project_path.join(p);
                if !f.is_file() {
                    bail!("PoC file not found or not a file: {}", f.display());
                }
                Ok(f)
            })
            .collect::<Result<Vec<_>, _>>()?;

        // Resolve crash report paths (best-effort; missing files are silently skipped)
        let crash_report_files = metadata
            .task_description
            .crash_report
            .as_ref()
            .map(|reports| {
                reports
                    .iter()
                    .map(|p| project_path.join(p))
                    .collect::<Vec<_>>()
            });

        // Validate source directory
        let source_folder = metadata.source.clone();
        if !source_folder.is_dir() {
            bail!("source directory not found: {}", source_folder.display());
        }

        // Validate and resolve script paths
        let scripts = Scripts {
            build: resolve_script(project_path, &metadata.scripts.build)?,
            run: resolve_script(project_path, &metadata.scripts.run)?,
            test: resolve_script(project_path, &metadata.scripts.test)?,
        };

        // Resolve optional file paths
        let intent_test_file = metadata
            .files
            .intent_test
            .as_ref()
            .map(|p| project_path.join(p));
        let ground_truth_patch_file = metadata.files.patch.as_ref().map(|p| project_path.join(p));

        Ok(BenchCore {
            metadata,
            source_folder,
            scripts,
            crash_report_files,
            intent_test_file,
            ground_truth_patch_file,
        })
    }

    /// Get reference to metadata
    pub fn metadata(&self) -> &Metadata {
        &self.metadata
    }

    /// Get source folder path
    pub fn source_folder(&self) -> &Path {
        &self.source_folder
    }

    /// Get resolved script paths
    pub fn scripts(&self) -> &Scripts {
        &self.scripts
    }

    /// Get intention test file path if available
    pub fn intent_test_patch(&self) -> Option<&Path> {
        self.intent_test_file.as_deref()
    }

    /// Get ground truth patch file path if available
    /// Note: This is the "answer" and should ONLY be exposed to WebUI, never to agents
    pub fn ground_truth_patch_file(&self) -> Option<&Path> {
        self.ground_truth_patch_file.as_deref()
    }

    /// Build the public metadata view, including script and report file contents.
    pub fn public_metadata(&self) -> PublicMetadata {
        let read_lossy =
            |p: &PathBuf| String::from_utf8_lossy(&fs::read(p).unwrap_or_default()).into_owned();

        let build_script = self.scripts.build.as_ref().map(&read_lossy);
        let test_script = self.scripts.test.as_ref().map(&read_lossy);

        let td = &self.metadata.task_description;
        let crash_report = self
            .crash_report_files
            .as_ref()
            .map(|reports| reports.iter().map(&read_lossy).collect());

        let task_description = PublicTaskDescription {
            issue: td.issue.clone(),
            crash_report,
            bug_description: td.bug_description.clone(),
        };

        PublicMetadata {
            id: self.metadata.id.clone(),
            project: self.metadata.project.clone(),
            language: self.metadata.language.clone(),
            source: self.metadata.source.clone(),
            task_description,
            poc: self.metadata.files.poc.clone(),
            build_script,
            test_script,
        }
    }

    /// Compute capabilities for the current benchmark case.
    pub fn capabilities(&self) -> Capabilities {
        let has_test_script = self.scripts.test.is_some();
        Capabilities {
            can_build: self.scripts.build.is_some(),
            can_run_poc: self.scripts.run.is_some() && !self.metadata.files.poc.is_empty(),
            poc_count: self.metadata.files.poc.len(),
            has_function_test: has_test_script,
            has_intent_test: has_test_script && self.intent_test_file.is_some(),
        }
    }
}

/// Load metadata from a file path.
fn load_metadata_from_file(metadata_file: &Path) -> Result<Metadata> {
    let contents = fs::read_to_string(metadata_file)?;
    load_metadata(&contents).map_err(|e| anyhow!("invalid config: {}", e))
}

/// Resolve an optional script path relative to the project directory.
///
/// Returns `Ok(Some(absolute_path))` if the script is configured and the file exists,
/// `Ok(None)` if the script is not configured, or an error if the file does not exist.
fn resolve_script(project_path: &Path, script: &Option<PathBuf>) -> Result<Option<PathBuf>> {
    match script {
        Some(rel_path) => {
            let full_path = project_path.join(rel_path);
            if full_path.is_file() {
                Ok(Some(full_path))
            } else {
                bail!("script not found: {}", full_path.display())
            }
        }
        None => Ok(None),
    }
}
