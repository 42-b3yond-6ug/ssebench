"""Evaluator module for SSEBench MCP Server.

This module provides patch evaluation functionality using the SSE SDK
to communicate with the daemon for build and test operations.
"""

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from sse import project

from config import TestConfig

# Prompt constants for actionable feedback
ALL_TESTS_SUCCESS_PROMPT = "Test succeeded: All checks passed. Your patch is valid. You may stop now."

BUILD_FAILED_PROMPT = "The project failed to build. Please reassess the correctness of your patch."
TEST_FAILED_PROMPT = (
    "One or more functionality test(s) failed. Please reassess your patch and make "
    "sure it fixes the vulnerability without compromising the program's functionality."
)
SECURITY_TEST_FAILED_PROMPT = (
    "The project failed to pass the proof-of-vulnerabilities test, only {pov_passed} "
    "out of {pov_total} proof-of-vulnerabilities didn't trigger a crash. Please "
    "reassess your patch and make sure it fixes the root cause of the vulnerability."
)
INTENT_TEST_FAILED_PROMPT = (
    "One or more intent test(s) failed. These tests validate behavior after "
    "the vulnerability fix. Please reassess your patch to ensure it correctly "
    "addresses the vulnerability and aligns with common patterns in the project."
)

LOG_FOLDER = Path(os.getenv("MCP_LOG_DIR", "/tmp/mcp/logs"))
MAXIMUM_FULL_LOG_WORD_COUNT = 10_000

os.makedirs(LOG_FOLDER, mode=0o755, exist_ok=True)


@dataclass
class PatchResult:
    """Result of evaluating a patch."""

    config: TestConfig
    pov_total: int

    build_success: bool | None = None
    pov_passed: int | None = field(default=0)
    func_test_success: bool | None = None
    intent_test_success: bool | None = None
    error_type: int | None = None
    error_log: str | None = None

    def ok(self) -> bool:
        """Check if all ENABLED tests passed."""
        if self.config.enable_build:
            if not self.build_success:
                return False

        if self.config.enable_security_test:
            passed = self.pov_passed if self.pov_passed else 0
            if passed < self.pov_total:
                return False

        if self.config.enable_function_test:
            if not self.func_test_success:
                return False

        if self.config.enable_intent_test:
            if not self.intent_test_success:
                return False

        return True

    def __str__(self) -> str:
        """Return actionable feedback for the agent."""
        if self.ok():
            return ALL_TESTS_SUCCESS_PROMPT

        # Determine the specific failure reason
        problem = "An internal testing failure occurred."

        if self.config.enable_build and not self.build_success:
            problem = BUILD_FAILED_PROMPT

        elif self.config.enable_function_test and not self.func_test_success:
            problem = TEST_FAILED_PROMPT

        elif self.config.enable_security_test and (self.pov_passed or 0) < self.pov_total:
            problem = SECURITY_TEST_FAILED_PROMPT.format(pov_passed=self.pov_passed, pov_total=self.pov_total)

        elif self.config.enable_intent_test and not self.intent_test_success:
            problem = INTENT_TEST_FAILED_PROMPT

        if self.error_log is None:
            return f"Test failed: {problem}\n\nFull log:\nNo log available"

        if len(self.error_log.split()) <= MAXIMUM_FULL_LOG_WORD_COUNT:
            return f"Test failed: {problem}\n\nFull log:\n{self.error_log}"

        logfile = LOG_FOLDER / f"{uuid.uuid4()}.txt"

        # Try to save full log, but handle failures gracefully
        log_saved = False
        try:
            with open(logfile, "w") as f:
                _ = f.write(self.error_log)
            os.chmod(logfile, 0o644)
            log_saved = True
        except OSError:
            pass  # Log could not be saved, will inform agent below

        # Use the more conservative truncation: shorter of last N lines vs last M words
        lines = self.error_log.split("\n")
        words = self.error_log.split()

        truncated_by_lines = "\n".join(lines[-100:])
        truncated_by_words = " ".join(words[-MAXIMUM_FULL_LOG_WORD_COUNT:])

        # Pick whichever truncation is shorter to avoid exceeding context limits
        truncated_log = truncated_by_lines if len(truncated_by_lines) <= len(truncated_by_words) else truncated_by_words

        if log_saved:
            return f"Test failed: {problem}\n\nTruncated log:\n{truncated_log}\n\nFull log available at {logfile}"
        else:
            return f"Test failed: {problem}\n\nTruncated log:\n{truncated_log}\n\n(Full log could not be saved due to an internal error)"


def _step_build(result: PatchResult) -> bool:
    """Build the project and update the result.

    Returns:
        True if build succeeded, False otherwise.
    """
    print("[mcp] Building project...")

    build_result = project.build()

    result.build_success = build_result.is_success()
    if not result.build_success:
        result.error_log = f"{build_result.stdout}\n\n{build_result.stderr}"
        return False

    return True


def _step_func_tests(result: PatchResult) -> bool:
    """Run functional tests and update the result.

    Returns:
        True if tests passed, False on failure.
    """
    print("[mcp] Running functional tests...")

    test_result = project.function_test()

    result.func_test_success = test_result.is_success()
    if not result.func_test_success:
        result.error_log = f"{test_result.stdout}\n\n{test_result.stderr}"
        return False

    return True


def _step_pocs(result: PatchResult) -> bool:
    """Run PoC tests and update the result.

    Returns early on the first PoC failure.

    Returns:
        True if all PoCs passed, False on first failure.
    """
    print("[mcp] Running PoC tests...")

    all_pocs = project.all_poc or []

    if len(all_pocs) == 0:
        return True

    result.pov_passed = 0
    for poc in all_pocs:
        run_result = project.run_poc(poc)
        if not run_result.is_success():
            result.error_log = f"{run_result.stdout}\n\n{run_result.stderr}"
            return False
        result.pov_passed += 1

    return True


def _step_intent_tests(result: PatchResult) -> bool:
    """Run intent tests and update the result.

    Returns:
        True if tests passed, False on failure.
    """
    print("[mcp] Running post tests...")

    test_result = project.intent_test()

    result.intent_test_success = test_result.is_success()
    if not result.intent_test_success:
        result.error_log = f"{test_result.stdout}\n\n{test_result.stderr}"
        return False

    return True


async def test_patch_internal(config: TestConfig) -> PatchResult:
    """Test a patch with the given configuration.

    This runs the evaluation pipeline based on the difficulty level:
    - Build the project (if enabled)
    - Run PoC tests (if enabled)
    - Run post tests (if enabled)
    - Run functional tests (if enabled)

    Early return behavior:
    - Build failure: early return (all other tests depend on build)
    - POC failure: continue (post/func tests are independent)
    - Post test failure: continue (func test may still pass)
    - Post test success: early return (func test must pass by definition)

    Args:
        config: TestConfig specifying which steps to run.

    Returns:
        PatchResult with the evaluation results.
    """
    all_pocs = project.all_poc or []
    result = PatchResult(config=config, pov_total=len(all_pocs))

    # Build step - early return on failure (others depend on build)
    if config.enable_build:
        result.build_success = False
        if not await asyncio.to_thread(_step_build, result):
            return result

    # PoC tests - continue regardless of result
    if config.enable_security_test:
        result.pov_passed = 0
        await asyncio.to_thread(_step_pocs, result)

    # Post tests
    if config.enable_intent_test:
        result.intent_test_success = False
        await asyncio.to_thread(_step_intent_tests, result)

    # Early return: intent test passed implies func test would pass
    if result.intent_test_success:
        if config.enable_function_test:
            result.func_test_success = True
        return result

    # Functional tests (only reached if post test disabled/failed)
    if config.enable_function_test:
        result.func_test_success = False
        await asyncio.to_thread(_step_func_tests, result)

    return result
