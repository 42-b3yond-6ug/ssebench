"""Evaluator module for SSEBench MCP Server.

This module provides patch evaluation functionality using the SSE SDK
to communicate with the daemon for build and test operations.
"""

import asyncio

from sse import project

from config import TestConfig
from patch_report import BUILD, FUNCTIONAL_TESTS, INTENT_TESTS, POCS, PatchResult


def _step_build(result: PatchResult) -> bool:
    """Build the project and update the result.

    Returns:
        True if build succeeded, False otherwise.
    """
    print("[mcp] Building project...")

    build_result = project.build()

    result.build_success = build_result.is_success()
    if not result.build_success:
        result.logs[BUILD] = f"{build_result.stdout}\n\n{build_result.stderr}"
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
        result.logs[FUNCTIONAL_TESTS] = f"{test_result.stdout}\n\n{test_result.stderr}"
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
            result.logs[POCS] = f"{run_result.stdout}\n\n{run_result.stderr}"
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
        result.logs[INTENT_TESTS] = f"{test_result.stdout}\n\n{test_result.stderr}"
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
