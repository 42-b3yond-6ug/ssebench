from pathlib import Path

from pydantic import BaseModel, field_validator, model_validator
from pydantic_core.core_schema import FieldValidationInfo


class TaskDescription(BaseModel):
    issue: str | None = None
    crash_report: list[str] | None = None
    bug_description: str | None = None

    @field_validator("issue", "bug_description")
    @classmethod
    def allow_empty_but_strip(cls, v: str | None) -> str | None:
        # strip strings if provided
        if isinstance(v, str):
            v = v.strip()
        return v

    @model_validator(mode="after")
    def at_least_one_filled(self) -> "TaskDescription":
        if not (self.issue or self.crash_report or self.bug_description):
            raise ValueError("At least one of issue, crash_report, bug_description must be provided")
        return self


class Files(BaseModel):
    patch: str | None = None
    future_test: str | None = None
    poc: list[str] | None = None


class TaskMetadata(BaseModel):
    id: str
    project: str
    language: str
    source: str
    task_description: TaskDescription
    scripts: dict[str, Path]
    files: Files

    @field_validator("id", "project", "language", "source")
    @classmethod
    def non_empty_str(cls, v: str, field: FieldValidationInfo) -> str:
        v = v.strip()
        if not v.strip():
            raise ValueError(f"{field.field_name} must be a non-empty string")
        return v
