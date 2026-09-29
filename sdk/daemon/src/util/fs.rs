use std::path::Path;

use anyhow::Result;
use fs_more::directory::{DirectoryCopyOptions, copy_directory};
use tempfile::TempDir;

/// Copy a folder to a temporary directory.
pub fn copy_folder_to_temp(source_path: &Path) -> Result<TempDir> {
    let temp_dir = TempDir::new()?;
    let destination_path = temp_dir.path();
    let options = DirectoryCopyOptions::default();

    copy_directory(source_path, destination_path, options)?;

    Ok(temp_dir)
}
