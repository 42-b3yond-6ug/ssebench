"""Reference patch access for tooling that runs as root in the task container.

WARNING: This exposes the reference patch (the answer). The daemon serves
``/reference/patch`` only on its privileged admin socket, which only root in
the task container can reach; the agent-facing listeners refuse it at all
times. Tools on the host read the patch from the task folder, or from
``reference.patch`` in the run's results directory.
"""

from __future__ import annotations

import os

from sse.daemon import Daemon

DEFAULT_ADMIN_SOCKET = "/run/ssebench/admin.sock"


def get_reference_patch() -> str:
    """Return the reference patch as a unified diff string.

    Calls ``/reference/patch`` on the daemon's admin socket, ``SSE_ADMIN_SOCKET``
    (default ``/run/ssebench/admin.sock``), so the caller must run as root in the
    task container. Returns an empty string if no reference patch is configured
    for the task.
    """
    socket = os.getenv("SSE_ADMIN_SOCKET") or DEFAULT_ADMIN_SOCKET
    data = Daemon(socket).get("/reference/patch")
    return data.get("diff", "")
