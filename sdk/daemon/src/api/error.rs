use std::fmt;

use actix_web::{HttpResponse, ResponseError};
use log::error;
use serde::Serialize;

#[derive(Serialize)]
struct ErrorResponse {
    error: String,
}

/// Application error that converts anyhow errors to HTTP responses.
#[derive(Debug)]
pub struct AppError(anyhow::Error);

impl fmt::Display for AppError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl From<anyhow::Error> for AppError {
    fn from(err: anyhow::Error) -> Self {
        AppError(err)
    }
}

impl ResponseError for AppError {
    fn error_response(&self) -> HttpResponse {
        error!("Request failed: {}", self.0);
        HttpResponse::InternalServerError().json(ErrorResponse {
            error: self.0.to_string(),
        })
    }
}
