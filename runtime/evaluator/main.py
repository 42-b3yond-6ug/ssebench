import asyncio
import logging
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from sse.grading import PatchResult as SDKPatchResult
from sse.grading import grade

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

logger = logging.getLogger()
logger.setLevel(logging.INFO)

NO_CHECK_RAN = "No check ran"


class PatchResult(BaseModel):
    status: Literal["passed", "failed", "error"]
    build_success: bool | None = None
    pov_passed: int | None = None
    pov_total: int | None = None
    func_test_success: bool | None = None
    intent_test_success: bool | None = None
    error_msg: str | None = None
    error_log: str | None = None

    @classmethod
    def from_sdk(cls, sdk_result: SDKPatchResult) -> "PatchResult":
        status = sdk_result.status()
        return cls(
            status=status,
            build_success=sdk_result.build_success,
            pov_passed=sdk_result.pov_passed,
            pov_total=sdk_result.pov_total,
            func_test_success=sdk_result.func_test_success,
            intent_test_success=sdk_result.intent_test_success,
            error_msg=sdk_result.error_msg or (NO_CHECK_RAN if status == "error" else None),
            error_log=sdk_result.error_log,
        )

    @classmethod
    def not_graded(cls, error_msg: str) -> "PatchResult":
        return cls(status="error", error_msg=error_msg)


class RuntimeResult(BaseModel):
    agent_duration: int
    agent_timeout: bool
    evaluator_timeout: bool
    # None when the entrypoint did not say, as with one that predates the variable.
    agent_exit_code: int | None = None


class EvaluationResult(BaseModel):
    patch_result: PatchResult
    runtime_result: RuntimeResult


async def run_grading(timeout: float, grade_patch: Callable[[], SDKPatchResult] = grade) -> tuple[PatchResult, bool]:
    """Grade the agent's patch within timeout seconds.

    Returns the result and whether grading timed out. A grading that raised or
    timed out ran no check to completion, so its result is an error.
    """
    try:
        sdk_result = await asyncio.wait_for(asyncio.to_thread(grade_patch), timeout=timeout)
    except TimeoutError:
        logger.error(f"[evaluator] Timeout after {timeout}s")
        return PatchResult.not_graded(f"Timeout ({timeout}s)"), True
    except Exception as e:
        logger.error(f"[evaluator] Unexpected Error: {e}", exc_info=True)
        return PatchResult.not_graded(f"Exception: {e!s}"), False
    return PatchResult.from_sdk(sdk_result), False


def agent_exit_status() -> int | None:
    """The agent's exit status, which the entrypoint passes in AGENT_EXIT_STATUS."""
    value = os.getenv("AGENT_EXIT_STATUS", "")
    return int(value) if value.lstrip("-").isdigit() else None


def result_path() -> Path:
    """Where the grade goes: result.json in the root-only results directory.

    Without SSE_RESULTS (a container started by an older runner), /sse_result.
    """
    results = os.getenv("SSE_RESULTS")
    return Path(results) / "result.json" if results else Path("/sse_result")


def write_result(content: str) -> None:
    """Write the grade in one step, so no reader sees a partial file."""
    path = result_path()
    if path == Path("/sse_result"):
        # A bind-mounted file cannot be replaced, only rewritten.
        _ = path.write_text(content)
        return
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".result-")
    try:
        with os.fdopen(fd, "w") as f:
            _ = f.write(content)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


async def main_async():
    # archive asks the daemon for the task on import.
    from archive import backup_src

    evaluator_timeout = int(os.getenv("TIMEOUT", 30 * 60))

    logger.info(f"[evaluator] Grading Start (Timeout: {evaluator_timeout}s)")

    patch_result, is_self_timeout = await run_grading(evaluator_timeout)

    match patch_result.status:
        case "passed":
            logger.info("[result] Patch success")
        case "failed":
            logger.warning("[result] Patch failed")
        case "error":
            logger.error(f"[result] Not graded: {patch_result.error_msg}")

    # Save Output
    await asyncio.to_thread(backup_src)

    agent_duration = int(os.getenv("AGENT_DURATION", "0"))
    agent_timeout_flag = os.getenv("SSE_METRIC_AGENT_TIMEOUT") is not None
    evaluation_result = EvaluationResult(
        patch_result=patch_result,
        runtime_result=RuntimeResult(
            agent_duration=agent_duration,
            agent_timeout=agent_timeout_flag,
            evaluator_timeout=is_self_timeout,
            agent_exit_code=agent_exit_status(),
        ),
    )

    try:
        write_result(evaluation_result.model_dump_json())
    except OSError as e:
        logger.error(f"Failed to write results: {e}")

    logger.info(evaluation_result.model_dump_json(indent=2))

    # In some cases, the test function may never terminate.
    # Without calling exit(0), the event loop will continue waiting until the thread completes.
    os._exit(0)


if __name__ == "__main__":
    asyncio.run(main_async())
