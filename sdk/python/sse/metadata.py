"""Types of the task's public metadata, as the daemon's ``GET /project`` and ``GET /capabilities``
return them.

They live apart from :mod:`sse.project`, which asks the daemon for them on import, so that code
built on them, such as :func:`sse.prompt.build_prompt`, works without a daemon.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dacite import Config, from_dict


@dataclass
class TaskDescription:
    """What the agent is told about the vulnerability."""

    issue: str | None
    """Issue text."""
    crash_report: list[str] | None
    """Contents of the report files, such as the upstream issue or a sanitizer log, in the order of
    the task config."""
    bug_description: str | None
    """Short description of the bug."""


@dataclass
class Metadata:
    """The task, as the daemon's ``GET /project`` returns it. Reference material is left out."""

    id: str
    """Task ID."""
    project: str
    """Name of the upstream project."""
    language: str
    """Language of the project: ``c``, ``go`` or ``rust``."""
    source: Path
    """The project's source tree, which the agent edits."""
    task_description: TaskDescription
    """What the agent is told about the vulnerability."""
    poc: list[Path]
    """Proof-of-concept inputs, to pass to :func:`sse.project.run_poc`. Only the daemon can read
    them."""
    build_script: str | None = None
    """Contents of the build script, if the task has one."""
    test_script: str | None = None
    """Contents of the test script, if the task has one."""


@dataclass
class Capabilities:
    """The checks the task supports, as the daemon's ``GET /capabilities`` returns them.

    The difficulty level can still withhold a supported check from the agent.
    """

    can_build: bool
    """The task has a build script."""
    can_run_poc: bool
    """The task has a run script and at least one proof of concept."""
    poc_count: int
    """Number of proofs of concept."""
    has_function_test: bool
    """The task has a test script."""
    has_intent_test: bool
    """The task has a test script and hidden tests of the fix."""


def parse_metadata(data: dict[str, Any]) -> Metadata:
    """Build :class:`Metadata` from the JSON object of the daemon's ``GET /project``."""
    return from_dict(Metadata, data, config=Config(cast=[Path]))
