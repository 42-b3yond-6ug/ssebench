"""Grading module for SSEBench SDK.

Runs all available tests for a benchmark case (based on capabilities)
and returns a structured PatchResult describing what passed and what failed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sse import tools
from sse.helper import ScriptResult


@dataclass
class PatchResult:
    """Structured result of grading a patch against all available tests.

    Fields are ``None`` when the corresponding step was not applicable
    (e.g. no build script configured).  A ``None`` value is *not* treated
    as a failure by :meth:`is_fully_successful`.
    """

    build_success: bool | None = None
    pov_passed: int | None = None
    pov_total: int | None = None
    func_test_success: bool | None = None
    intent_test_success: bool | None = None
    error_msg: str | None = None
    error_log: str | None = None

    def is_fully_successful(self) -> bool:
        """Return True when every *executed* step passed."""
        if self.build_success is not None and not self.build_success:
            return False
        if self.pov_total is not None and self.pov_passed != self.pov_total:
            return False
        if self.func_test_success is not None and not self.func_test_success:
            return False
        return not (
            self.intent_test_success is not None and not self.intent_test_success
        )

    def mark_failure(self, msg: str, log: str | None = None) -> None:
        """Record the *first* failure encountered.

        Subsequent calls are no-ops so the original failure context is
        preserved while later steps keep running.
        """
        if self.error_msg is not None:
            return
        self.error_msg = msg
        if log is not None:
            self.error_log = log


def _log_from(result: ScriptResult) -> str:
    """Combine stdout and stderr into a single log string."""
    return f"{result.stdout}\n{result.stderr}"


def grade() -> PatchResult:
    """Run all available tests and return a :class:`PatchResult`.

    The pipeline is driven entirely by the case's capabilities:

    1. **Build** -- early-return on failure (everything else depends on it).
    2. **Function test** -- runs the project's own test suite.
    3. **Security test** -- runs *all* PoCs, records how many passed.
    4. **Intent test** -- runs the test suite with the intent patch applied.

    Raises :class:`~sse.error.SDKError` on infrastructure failures
    (daemon unreachable, etc.) -- those are *not* test failures.
    """
    # Import here to avoid circular import at module level and to
    # allow the daemon to be started after the module is loaded.
    from sse.daemon import Daemon
    from sse.error import SDKError
    from sse.project import all_poc, capabilities

    result = PatchResult()

    # -- 0. Prepare source folder for grading ----------------------------
    # Captures the agent's diff, resets the repo, removes build artifacts
    # and other junk, then re-applies only the meaningful code changes.
    # NOTE: We catch SDKError for "git apply failed" here intentionally.
    # If the agent produced a malformed or conflicting patch, the daemon
    # raises an error when applying it to $SSE_REPO_PATH. We treat this as
    # a grading failure (all test steps marked failed) rather than a crash,
    # because an unapplicable patch is a valid — if terminal — agent outcome.
    # All other SDKErrors (network issues, etc.) are re-raised as usual.
    try:
        Daemon().prepare_grading()
    except SDKError as e:
        if not e.message.startswith("git apply failed"):
            raise
        result.mark_failure("Patch apply failed", e.message)
        result.build_success = False
        result.func_test_success = False
        result.intent_test_success = False
        return result

    # -- 1. Build --------------------------------------------------------
    if capabilities.can_build:
        build_result = tools.bencher.build(grading=True)
        result.build_success = build_result.is_success()
        if not result.build_success:
            result.mark_failure("Build failed", _log_from(build_result))
            return result  # nothing else is meaningful without a build

    # -- 2. Security tests ----------------------------------------------------
    if capabilities.can_run_poc:
        pocs: list[Path] = all_poc or []
        result.pov_total = len(pocs)
        result.pov_passed = 0
        for poc in pocs:
            poc_result = tools.bencher.run_poc(poc, grading=True)
            if poc_result.is_success():
                result.pov_passed += 1
            else:
                result.mark_failure(
                    f"PoC failed: {poc}",
                    _log_from(poc_result),
                )

    # -- 3. Function test ------------------------------------------------
    if capabilities.has_function_test:
        func_result = tools.bencher.function_test(grading=True)
        result.func_test_success = func_result.is_success()
        if not result.func_test_success:
            result.mark_failure("Function test failed", _log_from(func_result))

    # -- 4. Intent test --------------------------------------------------
    if capabilities.has_intent_test:
        intent_result = tools.bencher.intent_test(grading=True)
        result.intent_test_success = intent_result.is_success()
        if not result.intent_test_success:
            result.mark_failure("Intent test failed", _log_from(intent_result))

    return result
