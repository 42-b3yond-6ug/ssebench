mod diff;
mod error;
mod grading;
mod handlers;
mod state;

pub use diff::record_baseline;
pub use error::AppError;
pub use handlers::{ROUTES, configure_routes};
pub use state::{Access, AppState, Difficulty};
