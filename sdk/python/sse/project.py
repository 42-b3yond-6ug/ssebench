"""The task of this container: its metadata, its capabilities and the checks an agent may run.

Importing this module asks the daemon for the task's metadata and capabilities, so it works only
where a daemon answers: inside a task container, or with ``SSE_DAEMON_SOCKET`` pointing at one.
The checks go to the daemon's agent-facing socket, which refuses those that the run's difficulty
level withholds: they raise :class:`~sse.error.SDKError`. The types of the metadata are in
:mod:`sse.metadata`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from sse import tools
from sse.daemon import Daemon
from sse.helper import ScriptResult
from sse.metadata import Capabilities as Capabilities
from sse.metadata import Metadata as Metadata
from sse.metadata import TaskDescription as TaskDescription
from sse.metadata import parse_metadata


def init_metadata() -> Metadata:
    """Ask the daemon for the task's metadata. Importing the module does this once; use :data:`metadata`."""
    return parse_metadata(cast(dict[str, Any], Daemon().project()))


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
