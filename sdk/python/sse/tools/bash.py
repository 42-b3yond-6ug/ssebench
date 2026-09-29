from __future__ import annotations

from sse.daemon import Daemon
from sse.helper import ScriptResult, wrap_result


@wrap_result(ScriptResult)
def execute(command: str | list[str]):
    """Execute a bash command, parsing string commands into argument lists."""
    return Daemon().tool("bash", "execute", {"command": command})
