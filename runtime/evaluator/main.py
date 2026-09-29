import asyncio
import logging
import os

from pydantic import BaseModel
from sse.grading import PatchResult as SDKPatchResult
from sse.grading import grade

from archive import backup_src

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class PatchResult(BaseModel):
    build_success: bool | None = None
    pov_passed: int | None = None
    pov_total: int | None = None
    func_test_success: bool | None = None
    intent_test_success: bool | None = None
    error_msg: str | None = None
    error_log: str | None = None

    @classmethod
    def from_sdk(cls, sdk_result: SDKPatchResult) -> "PatchResult":
        return cls(
            build_success=sdk_result.build_success,
            pov_passed=sdk_result.pov_passed,
            pov_total=sdk_result.pov_total,
            func_test_success=sdk_result.func_test_success,
            intent_test_success=sdk_result.intent_test_success,
            error_msg=sdk_result.error_msg,
            error_log=sdk_result.error_log,
        )

    def is_fully_successful(self) -> bool:
        if self.build_success is not None and not self.build_success:
            return False
        if self.pov_total is not None and self.pov_passed != self.pov_total:
            return False
        if self.func_test_success is not None and not self.func_test_success:
            return False
        return not (self.intent_test_success is not None and not self.intent_test_success)


class RuntimeResult(BaseModel):
    agent_duration: int
    agent_timeout: bool
    evaluator_timeout: bool


class EvaluationResult(BaseModel):
    patch_result: PatchResult
    runtime_result: RuntimeResult


async def main_async():
    evaluator_timeout = int(os.getenv("TIMEOUT", 30 * 60))
    is_self_timeout = False

    logger.info(f"[evaluator] Grading Start (Timeout: {evaluator_timeout}s)")

    try:
        sdk_result = await asyncio.wait_for(
            asyncio.to_thread(grade),
            timeout=evaluator_timeout,
        )
        patch_result = PatchResult.from_sdk(sdk_result)
    except TimeoutError:
        logger.error(f"[evaluator] Timeout after {evaluator_timeout}s")
        patch_result = PatchResult()
        patch_result.error_msg = f"Timeout ({evaluator_timeout}s)"
        is_self_timeout = True
    except Exception as e:
        logger.error(f"[evaluator] Unexpected Error: {e}", exc_info=True)
        patch_result = PatchResult()
        patch_result.error_msg = f"Exception: {e!s}"

    if patch_result.is_fully_successful():
        logger.info("[result] Patch success")
    else:
        logger.warning("[result] Patch Failed or Incomplete")

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
        ),
    )

    try:
        with open("/sse_result", "w") as f:
            _ = f.write(evaluation_result.model_dump_json())
    except OSError as e:
        logger.error(f"Failed to write results: {e}")

    logger.info(evaluation_result.model_dump_json(indent=2))

    # In some cases, the test function may never terminate.
    # Without calling exit(0), the event loop will continue waiting until the thread completes.
    os._exit(0)


if __name__ == "__main__":
    asyncio.run(main_async())
