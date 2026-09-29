from typing import Literal, Self

from pydantic import BaseModel

from ssebench.tasks.metadata import TaskMetadata


class PatchResult(BaseModel):
    build_success: bool | None = None
    pov_passed: int | None = None
    pov_total: int | None = None
    func_test_success: bool | None = None
    intent_test_success: bool | None = None
    error_msg: str | None = None
    error_log: str | None = None


class RuntimeResult(BaseModel):
    agent_duration: int
    agent_timeout: bool
    evaluator_timeout: bool


class EvaluationResult(BaseModel):
    patch_result: PatchResult
    runtime_result: RuntimeResult


class FrameworkResult(BaseModel):
    spend: float  # the spend of LLM


class RunConfig(BaseModel):
    agent: str
    model: str
    mode: Literal["sidecar", "sandbox"]
    timeout: int
    difficulty: int
    tool_layer: str | None = None  # set in sandbox mode; sidecar mode has fixed layers


class PerTaskEvaluationResult(BaseModel):
    """
    PerTaskEvaluationResult will be provided as JSON to Typst (PDF render) to generate the per-task report.
    """

    task: TaskMetadata
    config: RunConfig
    patch_result: PatchResult
    runtime_result: RuntimeResult
    spend: float

    @classmethod
    def build(
        cls,
        tm: TaskMetadata,
        rc: RunConfig,
        frs: FrameworkResult,
        crs: EvaluationResult,
    ) -> Self:
        return cls(
            task=tm,
            config=rc,
            patch_result=crs.patch_result,
            runtime_result=crs.runtime_result,
            spend=frs.spend,
        )
