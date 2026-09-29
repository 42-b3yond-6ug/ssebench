"""Error types for SSEBench SDK."""

from __future__ import annotations


class SDKError(Exception):
    """Raised when the SDK encounters an error from the daemon.

    This exception is raised for daemon communication failures, config errors,
    file not found, etc. - NOT for script execution failures (non-zero exit code).

    Script execution results (success or failure) are returned as ScriptResult.
    Use result.is_success() to check if the script succeeded.
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
