mod diff;
mod error;
mod grading;
mod handlers;
mod state;

pub use error::AppError;
pub use handlers::configure_routes;
pub use state::{Access, AppState, Difficulty};
