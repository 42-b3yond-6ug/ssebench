import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from ssebench.cli import main
from ssebench.dataset import schema
from ssebench.dataset.dockerfile import Dockerfile, DockerfileError
from ssebench.dataset.validate import validate_dataset
from ssebench.tasks.metadata import TaskMetadata

# This checkout: bench/tests/ is two levels below the repository root.
CHECKOUT = Path(__file__).resolve().parents[2]
PILOT = CHECKOUT / "datasets" / "pilot"
SCHEMA_DIR = CHECKOUT / "datasets" / "schema"

MakeTask = Callable[..., Path]
TaskConfig = Callable[[str], dict[str, Any]]


def run_cli(*argv: str) -> int:
    with pytest.raises(SystemExit) as exit_info:
        main(list(argv))
    code = exit_info.value.code
    assert isinstance(code, int)
    return code


def replace_from(task: Path, line: str) -> None:
    """Replace the FROM line of a task's Dockerfile."""
    dockerfile = task / "Dockerfile"
    _ = dockerfile.write_text(re.sub(r"(?m)^FROM .*$", lambda _: line, dockerfile.read_text()))


def errors_of(dataset: Path) -> str:
    report = validate_dataset(dataset)
    assert not report.ok
    return report.format_errors()


# The committed dataset and schemas


def test_pilot_tasks_are_valid() -> None:
    report = validate_dataset(PILOT)

    assert report.ok, report.format_errors()
    assert len(report.tasks) == 55


def test_committed_schemas_are_current() -> None:
    assert schema.stale_schemas(SCHEMA_DIR) == []


def test_task_schema_accepts_every_pilot_config() -> None:
    validator = Draft202012Validator(json.loads((SCHEMA_DIR / "task.schema.json").read_text()))
    configs = sorted(PILOT.glob("*/sse/config.yaml"))

    assert len(configs) == 55
    for config in configs:
        errors = [e.message for e in validator.iter_errors(yaml.safe_load(config.read_text()))]
        assert errors == [], config


@pytest.mark.parametrize(
    "change",
    [
        {"unknown": 1},
        {"repository": None},
        {"repository": "git@example.org:demo.git"},
        {"id": "has space"},
        {"source": "src/demo"},
        {"originality": "Self Craft"},
        {"task_description": {"issue": " "}},
        {"task_description": {"crash_report": []}},
        {"scripts": {"build": "scripts/build.sh", "lint": "scripts/lint.sh"}},
        {"files": {"poc": ["/ssebench/pocs/poc.bin"]}},
    ],
)
def test_model_and_schema_reject_the_same_configs(change: dict[str, Any], task_config: TaskConfig) -> None:
    config = {k: v for k, v in (task_config("demo") | change).items() if v is not None}
    validator = Draft202012Validator(json.loads(schema.render_schema(TaskMetadata)))

    assert validator.is_valid(task_config("demo"))
    assert not validator.is_valid(config)
    with pytest.raises(ValidationError):
        _ = TaskMetadata.model_validate(config)


# Task folder checks


def test_valid_task(tmp_path: Path, make_task: MakeTask) -> None:
    _ = make_task(tmp_path, "demo-1")

    report = validate_dataset(tmp_path)

    assert report.ok, report.format_errors()
    assert report.tasks[0].base == "base-generic-c:1.0.0"


def test_id_must_equal_folder_name(tmp_path: Path, make_task: MakeTask) -> None:
    _ = make_task(tmp_path, "demo-1", {"id": "GO-2024-0001"})

    assert "demo-1:\n  sse/config.yaml: id: 'GO-2024-0001' must equal the folder name" in errors_of(tmp_path)


def test_unknown_and_missing_keys(tmp_path: Path, make_task: MakeTask) -> None:
    _ = make_task(tmp_path, "demo-1", {"originality": "Self Craft", "repository": None, "notes": "x"})

    errors = errors_of(tmp_path)

    assert "sse/config.yaml: repository: Field required" in errors
    assert "sse/config.yaml: notes: unknown key" in errors
    assert "sse/config.yaml: originality: Input should be 'public' or 'crafted'" in errors


def test_referenced_files_must_be_in_the_image(tmp_path: Path, make_task: MakeTask, task_config: TaskConfig) -> None:
    files = task_config("demo-1")["files"] | {"intent_test": "diffs/intent.diff", "poc": ["pocs/poc.bin", "x.bin"]}
    _ = make_task(tmp_path, "demo-1", {"files": files})

    errors = errors_of(tmp_path)

    assert "files.intent_test: the Dockerfile puts no file of the task folder at /ssebench/diffs/intent.diff" in errors
    assert "files.poc[1]: the Dockerfile puts no file of the task folder at /ssebench/x.bin" in errors


def test_paths_may_not_leave_the_image_root(tmp_path: Path, make_task: MakeTask, task_config: TaskConfig) -> None:
    scripts = task_config("demo-1")["scripts"] | {"build": "../src/demo/build.sh"}
    _ = make_task(tmp_path, "demo-1", {"scripts": scripts})

    assert "scripts.build: ../src/demo/build.sh is outside /ssebench" in errors_of(tmp_path)


def test_base_image_must_come_from_the_registry(tmp_path: Path, make_task: MakeTask) -> None:
    _ = make_task(tmp_path, "a", dockerfile="FROM ubuntu:24.04\nCOPY sse/config.yaml /ssebench/config.yaml\n")
    _ = make_task(tmp_path, "b", dockerfile="FROM ${SSEBENCH_REGISTRY}/base\nCOPY sse /ssebench\n")

    errors = errors_of(tmp_path)

    assert "the last FROM must be ${SSEBENCH_REGISTRY}/<base image>, not ubuntu:24.04" in errors
    assert "FROM uses SSEBENCH_REGISTRY, but no ARG SSEBENCH_REGISTRY precedes it" in errors


@pytest.mark.parametrize(
    ("line", "base"),
    [
        ("FROM ${SSEBENCH_REGISTRY}/base-generic-c:latest", "base-generic-c:latest"),
        ("FROM ${SSEBENCH_REGISTRY}/base-generic-c", "base-generic-c"),
        ("FROM ${SSEBENCH_REGISTRY}/base-generic-c:${TAG}", "base-generic-c:${TAG}"),
    ],
)
def test_base_image_must_be_pinned(tmp_path: Path, make_task: MakeTask, line: str, base: str) -> None:
    replace_from(make_task(tmp_path, "demo-1"), line)

    assert f"the base image must have a version tag or a digest, not {base}" in errors_of(tmp_path)


@pytest.mark.parametrize(
    "line",
    [
        "ARG TAG=1.0.0\nFROM ${SSEBENCH_REGISTRY}/base-generic-c:${TAG}",
        "FROM ${SSEBENCH_REGISTRY}/base-generic-c@sha256:" + "0" * 64,
        "FROM ${SSEBENCH_REGISTRY}/base-generic-c:1.0.0@sha256:" + "0" * 64,
    ],
)
def test_pinned_base_images(tmp_path: Path, make_task: MakeTask, line: str) -> None:
    replace_from(make_task(tmp_path, "demo-1"), line)

    report = validate_dataset(tmp_path)

    assert report.ok, report.format_errors()


def test_dockerfile_must_copy_the_config(tmp_path: Path, make_task: MakeTask) -> None:
    _ = make_task(
        tmp_path, "demo-1", dockerfile="ARG SSEBENCH_REGISTRY\nFROM ${SSEBENCH_REGISTRY}/b\nCOPY missing /x\n"
    )

    errors = errors_of(tmp_path)

    assert "Dockerfile: copies missing, which does not exist" in errors
    assert "Dockerfile: must copy sse/config.yaml to /ssebench/config.yaml" in errors


def test_missing_files(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()

    errors = errors_of(tmp_path)

    assert "sse/config.yaml: missing" in errors
    assert "Dockerfile: missing" in errors


def test_ids_must_differ_in_more_than_case(tmp_path: Path, make_task: MakeTask) -> None:
    _ = make_task(tmp_path, "Demo")
    _ = make_task(tmp_path, "demo")

    assert "tasks Demo and demo would share the image name" in errors_of(tmp_path)


def test_empty_dataset(tmp_path: Path) -> None:
    assert "no task folders" in errors_of(tmp_path)


# CLI


def test_cli_validate(tmp_path: Path, make_task: MakeTask, capsys: pytest.CaptureFixture[str]) -> None:
    _ = make_task(tmp_path, "good")
    assert run_cli("dataset", "validate", str(tmp_path)) == 0
    assert "1 tasks are valid" in capsys.readouterr().out

    _ = make_task(tmp_path, "bad", {"id": "other"})
    assert run_cli("dataset", "validate", str(tmp_path)) == 1
    err = capsys.readouterr().err
    assert "bad:\n  sse/config.yaml: id: 'other' must equal the folder name" in err
    assert "1 of 2 tasks are invalid" in err


def test_cli_schema(tmp_path: Path) -> None:
    assert run_cli("dataset", "schema", "--check", "-o", str(tmp_path)) == 1
    assert run_cli("dataset", "schema", "-o", str(tmp_path)) == 0
    assert run_cli("dataset", "schema", "--check", "-o", str(tmp_path)) == 0
    assert (tmp_path / "task.schema.json").read_text() == (SCHEMA_DIR / "task.schema.json").read_text()


# Dockerfile reading


@pytest.mark.parametrize(
    ("dockerfile", "base"),
    [
        ("FROM example.org/base\n", "example.org/base"),
        ("FROM a\nRUN x\nFROM b:1\n", "b:1"),
        ("FROM --platform=linux/amd64 c AS build\n", "c"),
        ("FROM d:2 AS build\nFROM build\n", "d:2"),
        ("ARG REG=reg.test\nFROM ${REG}/base-c\n", "reg.test/base-c"),
        ("ARG SSEBENCH_REGISTRY=reg.test\nFROM $SSEBENCH_REGISTRY/base-c\n", "${SSEBENCH_REGISTRY}/base-c"),
        ("FROM $REG/base-c\n", "${REG}/base-c"),
        ("FROM a\nARG X=y\nFROM $X\n", "${X}"),
        ("from e\n", "e"),
    ],
)
def test_base_image(dockerfile: str, base: str) -> None:
    assert Dockerfile.parse(dockerfile).base == base


def test_no_from() -> None:
    with pytest.raises(DockerfileError):
        _ = Dockerfile.parse("# comment\nRUN true\n")


def test_resolve_copies(tmp_path: Path) -> None:
    for name in ("sse/build.sh", "sse/diffs/a.diff", "vendored/lib.rs", "one.txt"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        _ = (tmp_path / name).write_text(name)
    dockerfile = Dockerfile.parse(
        "FROM base AS first\n"
        "COPY one.txt /early/\n"
        "FROM first\n"
        "WORKDIR /ssebench\n"
        "COPY --chown=root:root sse/build.sh scripts/build.sh\n"
        "COPY sse/diffs \\\n  /ssebench/diffs\n"
        "COPY --from=builder /out /ssebench/out\n"
        'COPY ["./vendored", "/src/vendored"]\n'
    )

    assert dockerfile.resolve(tmp_path, "/ssebench/scripts/build.sh") == tmp_path / "sse/build.sh"
    assert dockerfile.resolve(tmp_path, "/ssebench/diffs/a.diff") == tmp_path / "sse/diffs/a.diff"
    assert dockerfile.resolve(tmp_path, "/src/vendored/lib.rs") == tmp_path / "vendored/lib.rs"
    assert dockerfile.resolve(tmp_path, "/early/one.txt") == tmp_path / "one.txt"
    assert dockerfile.resolve(tmp_path, "/ssebench/diffs/missing.diff") is None
    assert dockerfile.resolve(tmp_path, "/ssebench/out/x") is None
