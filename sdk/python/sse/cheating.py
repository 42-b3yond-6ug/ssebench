"""Deprecated alias for :mod:`sse.reference`.

Kept for one release. Import :mod:`sse.reference` and call
:func:`sse.reference.get_reference_patch` instead.
"""

from __future__ import annotations

import warnings

from sse.reference import get_reference_patch

warnings.warn(
    "sse.cheating is deprecated; use sse.reference instead",
    DeprecationWarning,
    stacklevel=2,
)


def get_ground_truth() -> str:
    """Deprecated alias for :func:`sse.reference.get_reference_patch`."""
    warnings.warn(
        "sse.cheating.get_ground_truth is deprecated; "
        "use sse.reference.get_reference_patch instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return get_reference_patch()


__all__ = ["get_ground_truth"]
