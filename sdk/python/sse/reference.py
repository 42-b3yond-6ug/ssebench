"""Reference patch access for post-agent tooling (grading, review, web UI).

WARNING: This exposes the reference patch (the answer). It must never be used
by an agent while it works. The daemon serves ``/reference/patch`` only on its
privileged admin socket or after the agent phase has ended, so a call made
during the agent phase over the agent-facing socket fails.
"""

from __future__ import annotations

from sse.daemon import Daemon


def get_reference_patch() -> str:
    """Return the reference patch as a unified diff string.

    Calls the daemon's ``/reference/patch`` endpoint. Returns an empty string
    if no reference patch is configured for the task.
    """
    data = Daemon().get("/reference/patch")
    return data.get("diff", "")
