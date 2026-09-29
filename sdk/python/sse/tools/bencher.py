from __future__ import annotations

from sse.daemon import Daemon
from sse.error import SDKError
from sse.helper import ScriptResult, wrap_result

_caps_cache: dict[str, object] = {}


def _capabilities() -> dict[str, object]:
    """Fetch capabilities from daemon (cached after first call)."""
    global _caps_cache
    if not _caps_cache:
        _caps_cache = Daemon().capabilities()
    return _caps_cache


def _check(cap_key: str, action: str) -> None:
    """Raise SDKError if the capability is not available for this case."""
    if not _capabilities().get(cap_key):
        raise SDKError(f"{action} is not available for this case")


@wrap_result(ScriptResult)
def build(*, grading: bool = False):
    _check("can_build", "build")
    return Daemon().tool("bencher", "build", {"grading": grading})


@wrap_result(ScriptResult)
def run_poc(poc, *, grading: bool = False):
    _check("can_run_poc", "run_poc")
    return Daemon().tool("bencher", "run_poc", {"poc": str(poc)})


@wrap_result(ScriptResult)
def function_test(*, grading: bool = False):
    _check("has_function_test", "function_test")
    return Daemon().tool("bencher", "function_test", {"grading": grading})


def intent_test(*, grading: bool = False) -> ScriptResult:
    _check("has_intent_test", "intent_test")
    # NOTE: Unlike other bencher functions, we selectively catch SDKError here.
    # During an intent test, the daemon applies a patch before running the test.
    # If the patch fails to apply (e.g., the agent modified files in a way that
    # makes the patch conflict), the daemon raises an SDKError with a message
    # starting with "git apply failed" rather than returning a ScriptResult.
    # We treat this specific error as an "intent failed" outcome (code=1) rather
    # than a hard error, because patch failure is a valid and expected result
    # when the agent's changes are incompatible with the developer's intended fix.
    # All other SDKErrors (network issues, malformed responses, etc.) are re-raised
    # so they are not silently swallowed.
    try:
        data = Daemon().tool("bencher", "intent_test", {"grading": grading})
    except SDKError as e:
        if not e.message.startswith("git apply failed"):
            raise
        return ScriptResult(code=1, stdout="", stderr=e.message)
    if data is None:
        raise SDKError("received None result from daemon")
    try:
        return ScriptResult(**data)
    except Exception:
        raise SDKError(f"unexpected response format: {data}") from None
