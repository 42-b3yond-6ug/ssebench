//! Running what the agent wrote without privileges.
//!
//! The daemon runs as root, so it can read the task's hidden material and
//! write the grade. The task scripts it runs for a check build and test the
//! agent's source tree, so they execute code the agent wrote. They run as a
//! dedicated runner account instead, in a private copy of what the check
//! needs (see [`TaskRunner`]). When the agent phase ends, the agent's own
//! processes are killed (see [`agent_account`]).

mod account;
mod exec;
mod fs;
mod runner;
mod task_files;

pub use account::{Account, agent_account, effective_uid, is_root, parse_passwd};
pub use exec::{TrackedGroup, kill_all_processes_of, kill_live_groups, processes_of, run_captured};
pub use fs::{copy_file, copy_tree, remove_tree};
pub use runner::{TaskRunner, Workspace, pristine_dir};
pub use task_files::TaskFiles;
