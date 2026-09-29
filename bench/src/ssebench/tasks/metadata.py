"""Schema of a task's `sse/config.yaml`.

`datasets/schema/task.schema.json` is exported from these models (`ssebench dataset schema`). Unknown
keys are rejected: the daemon reads the same file with a model that ignores them, so a misspelt key
would otherwise go unnoticed.
"""

from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

# Case image names are `case/<dataset>/<id>` lowercased, so an ID must be a valid image path component.
TASK_ID_PATTERN = r"^[A-Za-z0-9]+(?:(?:[._]|__|-+)[A-Za-z0-9]+)*$"

ImagePath = Annotated[str, Field(min_length=1, pattern=r"^[^/]")]
Text = Annotated[str, Field(pattern=r"\S")]


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TaskDescription(_Config):
    """What the agent is told about the vulnerability. At least one field must be set."""

    model_config = ConfigDict(
        json_schema_extra={
            "anyOf": [
                {"required": ["issue"], "properties": {"issue": {"type": "string", "pattern": r"\S"}}},
                {"required": ["crash_report"], "properties": {"crash_report": {"type": "array", "minItems": 1}}},
                {
                    "required": ["bug_description"],
                    "properties": {"bug_description": {"type": "string", "pattern": r"\S"}},
                },
            ]
        }
    )

    issue: str | None = Field(default=None, description="Issue text given to the agent.")
    crash_report: list[ImagePath] | None = Field(
        default=None, description="Report files given to the agent, such as the upstream issue or a sanitizer log."
    )
    bug_description: str | None = Field(default=None, description="Short description of the bug given to the agent.")

    @model_validator(mode="after")
    def at_least_one_filled(self) -> Self:
        if not (self.issue or self.crash_report or self.bug_description):
            raise ValueError("at least one of issue, crash_report and bug_description must be set")
        return self


class Scripts(_Config):
    """Scripts that the grader and the agent's test_patch tool run."""

    build: ImagePath | None = Field(default=None, description="Builds the project in the source directory.")
    run: ImagePath | None = Field(default=None, description="Runs the proof of concept given as its argument.")
    test: ImagePath | None = Field(default=None, description="Runs the project's tests.")


class Files(_Config):
    """Reference material. None of it is shown to the agent."""

    patch: ImagePath | None = Field(
        default=None, description="The upstream fix, as a diff against the source directory."
    )
    future_test: ImagePath | None = Field(
        default=None,
        description="Hidden tests of the fix, usually those added upstream, as a diff. The intent test applies it "
        "and runs scripts.test.",
    )
    security_test: ImagePath | None = Field(
        default=None,
        description="Regression test for the vulnerability, as a diff. Kept for reference: the grader does not "
        "apply it, and its security check runs the proofs of concept instead.",
    )
    intent_test: ImagePath | None = Field(
        default=None,
        description="Tests of the intended behaviour, as a diff. Kept for reference: the intent test uses future_test.",
    )
    poc: list[ImagePath] | None = Field(default=None, description="Proof-of-concept inputs, each run with scripts.run.")


class TaskMetadata(_Config):
    """A task's configuration, `sse/config.yaml` in the task folder.

    Paths are relative to /ssebench in the case image, which the task's Dockerfile fills from `sse/`.
    """

    model_config = ConfigDict(title="SSEBench task config")

    id: str = Field(pattern=TASK_ID_PATTERN, max_length=128, description="Task ID, equal to the task's folder name.")
    project: Text = Field(description="Name of the upstream project.")
    repository: str = Field(pattern=r"^https://\S+$", description="URL of the upstream repository.")
    language: str = Field(pattern=r"^[a-z][a-z0-9+]*$", description="Language of the project, lowercase: c, go, rust.")
    source: str = Field(pattern=r"^/\S*$", description="Absolute path of the project's source tree in the case image.")
    task_description: TaskDescription
    scripts: Scripts
    files: Files

    sanitizer: str | None = Field(default=None, description="Sanitizer the build enables, such as address.")
    type: str | None = Field(default=None, description="Class of the bug, such as Heap Buffer Overflow or a CWE.")
    binary: str | None = Field(default=None, description="Program or harness that the proofs of concept exercise.")
    trigger_commit: str | None = Field(default=None, description="Upstream revision that the case image builds.")
    patch_commit: str | None = Field(default=None, description="Upstream commits that fix the bug, comma-separated.")
    reference: list[str] | None = Field(default=None, description="Links to the advisory, the report and the fix.")
    originality: Literal["public", "crafted"] | None = Field(
        default=None,
        description="Origin of the proofs of concept: public when they come from the public report or advisory, "
        "possibly adapted; crafted when they were written for the task because the report has no reproducer.",
    )


def load_task_metadata(path: Path) -> TaskMetadata:
    """Read and validate a task config.

    Raises:
        OSError: If the file cannot be read.
        yaml.YAMLError: If it is not YAML.
        pydantic.ValidationError: If it does not match the schema.
    """
    with path.open() as f:
        return TaskMetadata.model_validate(yaml.safe_load(f))
