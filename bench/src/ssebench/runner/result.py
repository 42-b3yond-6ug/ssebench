from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from ssebench.runner.plugin_report import PluginOutcome
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


def describe_grade(r: PatchResult) -> str:
    """One line with the outcome of each check, such as `build passed, PoC 0/1 passed, ...`; a check that did not run says so."""

    def outcome(ok: bool | None) -> str:
        return "not run" if ok is None else "passed" if ok else "failed"

    poc = "PoC not run" if r.pov_total is None else f"PoC {r.pov_passed}/{r.pov_total} passed"
    return ", ".join(
        [
            f"build {outcome(r.build_success)}",
            poc,
            f"functional tests {outcome(r.func_test_success)}",
            f"intent tests {outcome(r.intent_test_success)}",
        ]
    )


class RuntimeResult(BaseModel):
    agent_duration: int
    agent_timeout: bool
    evaluator_timeout: bool


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
    # How each plugin that ran ended, from the container's plugin report.
    plugin_results: list[PluginOutcome] = []

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
