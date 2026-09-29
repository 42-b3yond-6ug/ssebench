import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from ssebench.cli import main
from ssebench.dataset.generate import build_manifest, checks, recorded_commit, render_manifest
from ssebench.dataset.validate import validate_dataset
from ssebench.tasks.manifest import Manifest
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


def schema_validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((SCHEMA_DIR / name).read_text()))


# The committed manifest


def test_committed_manifest_is_current() -> None:
    path = PILOT / "manifest.json"

    assert render_manifest(build_manifest(PILOT, recorded_commit(path))) == path.read_text()
    assert run_cli("dataset", "manifest", "--check", str(PILOT)) == 0


def test_committed_files_match_their_schemas() -> None:
    manifest = json.loads((PILOT / "manifest.json").read_text())

    assert list(schema_validator("manifest.schema.json").iter_errors(manifest)) == []
    info = yaml.safe_load((PILOT / "dataset.yaml").read_text())
    assert list(schema_validator("dataset.schema.json").iter_errors(info)) == []


def test_pilot_manifest() -> None:
    manifest = Manifest.model_validate_json((PILOT / "manifest.json").read_text())
    folders = sorted(p.name for p in PILOT.iterdir() if p.is_dir())

    assert (manifest.dataset, manifest.version) == ("pilot", "pilot-v1")
    assert [t.id for t in manifest.tasks] == folders
    for task in manifest.tasks:
        assert task.metadata.id == task.id
        assert task.image == f"case/pilot/{task.id.lower()}"
        assert task.base == f"base-generic-{task.language}:latest"
        assert task.checks == ["build", "poc", "function_test", "intent_test"]
        assert task.files is not None and "sse/config.yaml" in task.files


# Generation


def test_manifest_entry(tmp_path: Path, make_task: MakeTask) -> None:
    dataset = tmp_path / "demo"
    task = make_task(dataset, "Demo-1")

    manifest = build_manifest(dataset)

    assert (manifest.dataset, manifest.version, manifest.generated_from) == ("demo", "demo-v1", None)
    entry = manifest.tasks[0]
    assert entry.model_dump(exclude={"files", "metadata"}) == {
        "id": "Demo-1",
        "language": "c",
        "project": "demo",
        "repository": "https://example.org/demo",
        "base": "base-generic-c:latest",
        "image": "case/demo/demo-1",
        "arch": ["amd64"],
        "checks": ["build", "poc", "function_test", "intent_test"],
    }
    assert entry.files is not None
    assert list(entry.files) == sorted(entry.files)
    assert entry.files["sse/pocs/poc.bin"] == hashlib.sha256(b"crash\n").hexdigest()
    assert entry.metadata == TaskMetadata.model_validate(yaml.safe_load((task / "sse/config.yaml").read_text()))


def test_rendering_is_stable(tmp_path: Path, make_task: MakeTask) -> None:
    for task_id in ("b", "c", "A"):
        _ = make_task(tmp_path, task_id)

    text = render_manifest(build_manifest(tmp_path))
    data = json.loads(text)

    assert [t["id"] for t in data["tasks"]] == ["A", "b", "c"]
    assert "generated_from" not in data
    assert text.endswith("}\n")
    assert render_manifest(build_manifest(tmp_path)) == text
    assert render_manifest(Manifest.model_validate_json(text)) == text
    assert list(schema_validator("manifest.schema.json").iter_errors(data)) == []


@pytest.mark.parametrize(
    ("scripts", "files", "expected"),
    [
        ({}, {}, []),
        ({"build": "b", "run": "r"}, {}, ["build"]),
        ({"run": "r"}, {"poc": ["p"]}, ["poc"]),
        ({"test": "t"}, {"future_test": "f", "security_test": "s"}, ["function_test", "intent_test"]),
        ({}, {"future_test": "f"}, []),
    ],
)
def test_checks(task_config: TaskConfig, scripts: dict[str, str], files: dict[str, Any], expected: list[str]) -> None:
    metadata = TaskMetadata.model_validate(task_config("demo") | {"scripts": scripts, "files": files})

    assert checks(metadata) == expected


def test_invalid_dataset_has_no_manifest(
    tmp_path: Path, make_task: MakeTask, capsys: pytest.CaptureFixture[str]
) -> None:
    _ = make_task(tmp_path, "demo", {"id": "other"})

    assert run_cli("dataset", "manifest", str(tmp_path)) == 1
    assert "id: 'other' must equal the folder name" in capsys.readouterr().err
    assert not (tmp_path / "manifest.json").exists()


def test_dataset_info_is_required(tmp_path: Path, make_task: MakeTask) -> None:
    _ = make_task(tmp_path, "demo")
    _ = (tmp_path / "dataset.yaml").write_text("version: Pilot v1\nname: x\n")

    errors = validate_dataset(tmp_path).format_errors()
    assert "dataset.yaml: version: String should match pattern" in errors
    assert "dataset.yaml: name: unknown key" in errors

    (tmp_path / "dataset.yaml").unlink()
    assert "dataset.yaml: missing" in validate_dataset(tmp_path).format_errors()


# CLI


def test_cli_manifest_check(tmp_path: Path, make_task: MakeTask, capsys: pytest.CaptureFixture[str]) -> None:
    task = make_task(tmp_path, "demo")
    manifest = tmp_path / "manifest.json"

    assert run_cli("dataset", "manifest", "--check", str(tmp_path)) == 1
    assert run_cli("dataset", "manifest", str(tmp_path)) == 0
    assert "with 1 tasks" in capsys.readouterr().out
    assert run_cli("dataset", "manifest", "--check", str(tmp_path)) == 0

    _ = (task / "sse" / "pocs" / "poc.bin").write_text("another crash\n")
    assert run_cli("dataset", "manifest", "--check", str(tmp_path)) == 1
    err = capsys.readouterr().err
    assert '"sse/pocs/poc.bin"' in err
    assert f"{manifest} is out of date" in err


def test_cli_manifest_generated_from(tmp_path: Path, make_task: MakeTask) -> None:
    _ = make_task(tmp_path, "demo")
    manifest = tmp_path / "manifest.json"

    assert run_cli("dataset", "manifest", "--generated-from", "0123abc", str(tmp_path)) == 0
    assert json.loads(manifest.read_text())["generated_from"] == "0123abc"
    # --check compares against the commit the file records, which changes with every commit.
    assert run_cli("dataset", "manifest", "--check", str(tmp_path)) == 0
    assert run_cli("dataset", "manifest", "--check", "--generated-from", "4567def", str(tmp_path)) == 1


def test_cli_manifest_to_stdout(tmp_path: Path, make_task: MakeTask, capsys: pytest.CaptureFixture[str]) -> None:
    _ = make_task(tmp_path, "demo")

    assert run_cli("dataset", "manifest", "-o", "-", str(tmp_path)) == 0
    assert json.loads(capsys.readouterr().out)["tasks"][0]["id"] == "demo"
    assert not (tmp_path / "manifest.json").exists()
    assert run_cli("dataset", "manifest", "--check", "-o", "-", str(tmp_path)) == 2
