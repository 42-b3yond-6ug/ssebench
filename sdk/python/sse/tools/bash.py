"""The daemon's ``bash`` tool: one interactive shell in the source tree, as the unprivileged user."""

from __future__ import annotations

from sse.daemon import Daemon
from sse.helper import ScriptResult, wrap_result


@wrap_result(ScriptResult)
def execute(command: str):
    """Run ``command`` in the daemon's shell and wait for it to finish.

    The shell persists between calls, so ``cd`` and ``export`` carry over; ``exit`` ends it.
    """
    return Daemon().tool("bash", "execute", {"command": command})
