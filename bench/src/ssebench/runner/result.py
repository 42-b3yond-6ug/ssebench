from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from ssebench.tasks.metadata import TaskMetadata

GradeStatus = Literal["passed", "failed", "error"]


class PatchResult(BaseModel):
    # Derived from the checks when absent: the CLI's own no-result record,
    # and result.json from an evaluator that predates the field.
    status: GradeStatus | None = None
    build_success: bool | None = None
    pov_passed: int | None = None
    pov_total: int | None = None
    func_test_success: bool | None = None
    intent_test_success: bool | None = None
    error_msg: str | None = None
    error_log: str | None = None

    @model_validator(mode="after")
    def derive_status(self) -> Self:
        if self.status is None:
            self.status = grade_status(self)
        return self


def grade_status(r: PatchResult) -> GradeStatus:
    """`error` when no check ran, since nothing graded the patch; else whether every check that ran passed."""
    if all(v is None for v in (r.build_success, r.pov_total, r.func_test_success, r.intent_test_success)):
        return "error"
    failed = (
        r.build_success is False
        or (r.pov_total is not None and r.pov_passed != r.pov_total)
        or r.func_test_success is False
        or r.intent_test_success is False
    )
    return "failed" if failed else "passed"


class RuntimeResult(BaseModel):
    agent_duration: int
    agent_timeout: bool
    evaluator_timeout: bool
    # The agent's exit status, 124 after a timeout. None when the evaluator did not record one.
    agent_exit_code: int | None = None


class RunConfig(BaseModel):
    agent: str
    model: str
    mode: Literal["sidecar", "sandbox"]
    timeout: int
    difficulty: int = Field(ge=0, le=4)
    tool_layer: str | None = None  # set in sandbox mode; sidecar mode has fixed layers
    egress: Literal["restricted", "open"] = "restricted"
    # The reference agent applied the task's known fix: the grade measures the task, not a model.
    reference_run: bool = False
    plugins: list[str] = []  # plugins enabled for the run, in plugins.yaml order


class EvaluationResult(BaseModel):
    """result.json: the evaluator's grade, to which `ssebench run` adds the run settings."""

    patch_result: PatchResult
    runtime_result: RuntimeResult
    config: RunConfig | None = None


def model_never_answered(result: EvaluationResult, spend: float) -> str | None:
    """Why the run says nothing about the model, or None when it does.

    An agent that exits non-zero while the proxy booked no spend for the run was not answered by the
    model: the provider key may be invalid, or the provider down. Its grade is that of the unmodified
    project, which a model that tried and failed also gets, so the run is an error, not a failure.
    """
    code = result.runtime_result.agent_exit_code
    if code is None or code == 0 or spend > 0:
        return None
    return (
        f"The agent exited with status {code} and the model answered no call (spend {spend}), so this run does "
        "not show what the model can do; check the provider key and the agent's log"
    )


class FrameworkResult(BaseModel):
    spend: float  # the spend of LLM


class PerTaskEvaluationResult(BaseModel):
    """
    PerTaskEvaluationResult will be provided as JSON to Typst (PDF render) to generate the per-task report.
    """

    task: TaskMetadata
    config: RunConfig
    patch_result: PatchResult
    runtime_result: RuntimeResult
    spend: float
    # The name of the run's directory under results/<task>/<model>/<agent>/, and when its container
    # was started, in UTC: what orders the runs of one task, model and agent.
    run_id: str | None = None
    started_at: datetime | None = None

    @classmethod
    def build(
        cls,
        tm: TaskMetadata,
        rc: RunConfig,
        frs: FrameworkResult,
        crs: EvaluationResult,
        run_id: str | None = None,
        started_at: datetime | None = None,
    ) -> Self:
        return cls(
            task=tm,
            config=rc,
            patch_result=crs.patch_result,
            runtime_result=crs.runtime_result,
            spend=frs.spend,
            run_id=run_id,
            started_at=started_at,
        )
