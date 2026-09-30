"""Where the files of a run go under `results/`; the one place that knows the layout.

```
results/<task>/<model>/<agent>/<run-id>/     one directory per run
results/<task>/<model>/<agent>/latest        link to the newest of them
```

A run directory holds the container's outputs, `result.json` among them, and `summary.json`,
which `ssebench run` writes when the run ends. Two runs of the same task, model and agent have
different run IDs, so neither replaces the other.
"""

import logging
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

RESULTS_DIR = "results"
"""The results directory, relative to the working directory of `ssebench run`."""
SUMMARY_FILE = "summary.json"
LATEST = "latest"
"""The link that names the newest run directory of a task, model and agent."""


def new_run_id(now: datetime | None = None) -> str:
    """A run ID for a run that was not given one: the UTC time now and six random hex digits.

    IDs made this way sort in the order they were made.
    """
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    return f"{moment:%Y%m%d-%H%M%S}-{secrets.token_hex(3)}"


def group_dir(task: str, agent: str, model: str, root: Path = Path(RESULTS_DIR)) -> Path:
    """The directory of every run of `task` with `agent` and `model`."""
    return root / task / model / agent


def run_dir(task: str, agent: str, model: str, run_id: str, root: Path = Path(RESULTS_DIR)) -> Path:
    """The directory of one run."""
    return group_dir(task, agent, model, root) / run_id


def summary_path(task: str, agent: str, model: str, run_id: str, root: Path = Path(RESULTS_DIR)) -> Path:
    """The run summary that `ssebench run` writes, a PerTaskEvaluationResult."""
    return run_dir(task, agent, model, run_id, root) / SUMMARY_FILE


def mark_latest(directory: Path) -> None:
    """Point `latest`, beside the run directory `directory`, at it.

    The link is not inside the run directory, which a container writes to as root, so the host user
    can always replace it. Best effort: a file system without symbolic links loses the shortcut only.
    """
    link = directory.parent / LATEST
    scratch = directory.parent / f".{LATEST}.{os.getpid()}"
    try:
        scratch.unlink(missing_ok=True)
        scratch.symlink_to(directory.name)
        _ = scratch.replace(link)
    except OSError as e:
        logger.warning(f"Could not point {link} at {directory.name}: {e}")
        scratch.unlink(missing_ok=True)
