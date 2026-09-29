"""Cheating module — ground truth access for grading/review only.

WARNING: This module exposes the ground truth patch (the answer).
It must NEVER be used by agents during benchmark execution.
It is intended for post-hoc analysis, grading reviewers, and WebUI.
"""

from __future__ import annotations

from sse.daemon import Daemon


def get_ground_truth() -> str:
    """Return the ground truth patch as a unified diff string.

    Calls the daemon's ``/cheating/ground_truth`` endpoint.
    Returns an empty string if no ground truth patch is configured.
    """
    data = Daemon().get("/cheating/ground_truth")
    return data.get("diff", "")
