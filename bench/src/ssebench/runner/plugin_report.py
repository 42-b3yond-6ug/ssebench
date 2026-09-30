"""The outcome of each plugin of a run, as the container's entrypoint recorded it."""

import logging
from pathlib import Path

from pydantic import BaseModel, TypeAdapter, ValidationError

logger = logging.getLogger(__name__)

PLUGIN_REPORT = Path("plugins") / "results.json"


class PluginOutcome(BaseModel):
    name: str
    hook: str
    status: str  # ok, skipped, failed, timeout or error
    exit_code: int = 0
    duration_seconds: float = 0.0
    reason: str | None = None  # why a skipped plugin did not run
    error: str | None = None


def read_plugin_report(archive: Path) -> list[PluginOutcome]:
    """The plugins' outcomes in the run's archive directory; empty when no plugin ran."""
    path = archive / PLUGIN_REPORT
    try:
        return TypeAdapter(list[PluginOutcome]).validate_json(path.read_text())
    except FileNotFoundError:
        return []
    except (OSError, ValidationError) as e:
        logger.warning(f"Ignoring the unreadable plugin report {path}: {e}")
        return []
