from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from sse.error import SDKError

__all__ = [
    "SDKError",
    "ScriptResult",
    "wrap_result",
]

T = TypeVar("T")


def wrap_result(
    cls: type[T],
) -> Callable[[Callable[..., Any]], Callable[..., T]]:
    """Decorator to wrap daemon results into dataclass instances.

    Assumes daemon.py already handles error responses by raising SDKError.
    This decorator converts successful JSON responses to the specified class.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., T]:
        def wrapper(*args: Any, **kwargs: Any) -> T:
            data = func(*args, **kwargs)
            if data is None:
                raise SDKError("received None result from daemon")
            try:
                return cls(**data)
            except Exception:
                # Data doesn't match expected format
                raise SDKError(f"unexpected response format: {data}") from None

        return wrapper

    return decorator


@dataclass
class ScriptResult:
    """Result of a script execution.

    This represents a successful execution of a script (the script ran).
    Check is_success() to see if the script returned exit code 0.
    """

    code: int
    stdout: str
    stderr: str

    def __str__(self) -> str:
        return (
            f"Script execution completed with exit code {self.code}. "
            "Exit code 0 means success, non-zero indicates the script failed."
        )

    def is_success(self) -> bool:
        """Check if the script returned exit code 0."""
        return self.code == 0
