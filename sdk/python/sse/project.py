"""The task of this container: its metadata, its capabilities and the checks an agent may run.

Importing this module asks the daemon for the task's metadata and capabilities, so it works only
where a daemon answers: inside a task container, or with ``SSE_DAEMON_SOCKET`` pointing at one.
The checks go to the daemon's agent-facing socket, which refuses those that the run's difficulty
level withholds: they raise :class:`~sse.error.SDKError`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from dacite import Config, from_dict

from sse import tools
from sse.daemon import Daemon
from sse.helper import ScriptResult


@dataclass
class TaskDescription:
    """What the agent is told about the vulnerability."""

    issue: str | None
    """Issue text."""
    crash_report: list[str] | None
    """Contents of the report files, such as the upstream issue or a sanitizer log."""
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
    """Proof-of-concept inputs, to pass to :func:`run_poc`. Only the daemon can read them."""
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


def init_metadata() -> Metadata:
    """Ask the daemon for the task's metadata. Importing the module does this once; use :data:`metadata`."""
    m = cast(dict[str, Any], Daemon().project())
    return from_dict(Metadata, m, config=Config(cast=[Path]))


def init_capabilities() -> Capabilities:
    """Ask the daemon for the task's capabilities. Importing the module does this once; use :data:`capabilities`."""
    data = cast(dict[str, Any], Daemon().capabilities())
    return Capabilities(**data)


metadata: Metadata = init_metadata()
"""The task's metadata, fetched when the module is imported."""
capabilities: Capabilities = init_capabilities()
"""The task's capabilities, fetched when the module is imported."""
source: Path = metadata.source
"""The project's source tree, which the agent edits (``metadata.source``)."""
all_poc: list[Path] = metadata.poc
"""The task's proof-of-concept inputs (``metadata.poc``)."""


def build() -> ScriptResult:
    """Build the project from a copy of its source tree, and keep the build for :func:`run_poc`.

    Raises :class:`~sse.error.SDKError` when the task has no build script, when the difficulty
    level withholds the build, or when the daemon fails. A failed build is a result with a
    non-zero exit code, not an error.
    """
    return tools.bencher.build()


def run_poc(poc: Path) -> ScriptResult:
    """Run one proof of concept, one of :data:`all_poc`, against the last :func:`build`.

    Exit code 0 means that the vulnerability no longer triggers. Without a build the result has
    exit code -1. Raises :class:`~sse.error.SDKError` as :func:`build` does.
    """
    return tools.bencher.run_poc(poc)


def function_test() -> ScriptResult:
    """Run the project's tests on a copy of its source tree.

    Raises :class:`~sse.error.SDKError` as :func:`build` does.
    """
    return tools.bencher.function_test()


def intent_test() -> ScriptResult:
    """Apply the hidden tests of the fix to a copy of the source tree and run the project's tests.

    Hidden tests that do not apply to the agent's changes give exit code 1. Raises
    :class:`~sse.error.SDKError` as :func:`build` does.
    """
    return tools.bencher.intent_test()
