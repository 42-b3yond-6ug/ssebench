use crate::util::{copy_folder_to_temp, run_script};
use std::fs;
use tempfile::TempDir;

#[test]
fn test_run_script_success() {
    let result = run_script("echo", &["hello".to_string(), "world".to_string()], ".");
    assert!(result.is_ok());
    let script_result = result.unwrap();
    assert_eq!(script_result.code, 0);
    assert!(script_result.stdout.contains("hello world"));
    assert!(script_result.success());
}

#[test]
fn test_run_script_failure() {
    let result = run_script("false", &[], ".");
    assert!(result.is_ok());
    let script_result = result.unwrap();
    assert_eq!(script_result.code, 1);
    assert!(!script_result.success());
}

#[test]
fn test_run_script_nonexistent() {
    let result = run_script("nonexistent_command_12345", &[], ".");
    assert!(result.is_err());
    // Error message is from std::io::Error - "No such file or directory"
    let error = result.unwrap_err();
    assert!(
        error.to_string().to_lowercase().contains("not found")
            || error.to_string().to_lowercase().contains("no such file")
    );
}

#[test]
fn test_copy_folder_to_temp() {
    // Create a temporary source directory
    let source_temp = TempDir::new().unwrap();
    let source_path = source_temp.path();

    // Create a test file in the source directory
    let test_file = source_path.join("test.txt");
    fs::write(&test_file, "test content").unwrap();

    // Copy to temporary directory
    let result = copy_folder_to_temp(source_path);
    assert!(result.is_ok());

    let dest_temp = result.unwrap();
    let copied_file = dest_temp.path().join("test.txt");

    // Verify file was copied
    assert!(copied_file.exists());
    let content = fs::read_to_string(&copied_file).unwrap();
    assert_eq!(content, "test content");
}

#[test]
fn test_copy_nonexistent_folder() {
    let result = copy_folder_to_temp(std::path::Path::new("/nonexistent/path"));
    assert!(result.is_err());
}
