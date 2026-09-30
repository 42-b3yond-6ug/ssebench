"""The run directory: one for each run, the grade and the logs root-only in the container, the agent's files
apart, the summary beside them, and the reference patch added from the task folder once the run is over."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ssebench.agents import Agent
from ssebench.backends import ARCHIVE_PATH, RESULTS_LABEL, RESULTS_PATH, DockerBackend, Images
from ssebench.errors import UserError
from ssebench.models import NoModel
from ssebench.runner import BenchmarkSandboxRunner, BenchmarkSidecarRunner
from ssebench.runner.layout import LATEST
from ssebench.runner.result import RunConfig
from ssebench.runner.runner import prepare_run_directory, record_results, save_reference_patch
from ssebench.tasks import LocalTask

from .conftest import FakeDocker

TASK = "demo-1"


@pytest.fixture
def task(tmp_path: Path, make_task: Callable[..., Path]) -> LocalTask:
    dataset = tmp_path / "pilot"
    _ = make_task(dataset, TASK)
    return LocalTask(TASK, dataset)


def options(cmd: list[str], flag: str) -> list[str]:
    return [cmd[i + 1] for i, arg in enumerate(cmd) if arg == flag]


def test_a_new_run_directory_has_an_archive_and_an_empty_result(tmp_path: Path) -> None:
    run_dir = tmp_path / "group" / "run"

    result = prepare_run_directory(run_dir)

    assert result == run_dir / "result.json" and result.read_text() == ""
    assert sorted(p.name for p in run_dir.iterdir()) == ["archive", "result.json"]
    assert not list((run_dir / "archive").iterdir())


def test_a_run_directory_that_exists_is_never_reused(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "archive").mkdir(parents=True)
    _ = (run_dir / "archive" / "dialog.jsonl").write_text("{}\n")

    with pytest.raises(UserError, match="already has results"):
        _ = prepare_run_directory(run_dir)

    assert (run_dir / "archive" / "dialog.jsonl").read_text() == "{}\n"


def test_the_sandbox_container_gets_the_results_root_only_and_the_archive_apart(
    task: LocalTask, tmp_path: Path
) -> None:
    runner = BenchmarkSandboxRunner(NoModel(), Agent("dummy", task_name=TASK), task, 60, 2)
    runner.images = Images(agent="registry.test/image")
    run_dir = tmp_path / "run"

    cmd = DockerBackend().run_command(runner.run_spec(run_dir, None))

    assert options(cmd, "-v") == [f"{run_dir}:{RESULTS_PATH}", f"{run_dir / 'archive'}:{ARCHIVE_PATH}"]
    assert f"{RESULTS_LABEL}={run_dir}" in options(cmd, "--label")
    assert not [arg for arg in cmd if "/sse_result" in arg]


def test_the_reference_patch_is_saved_from_the_task_folder(task: LocalTask, tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    save_reference_patch(task, run_dir)
    assert (run_dir / "reference.patch").read_text() == "fix\n"


def test_a_task_without_a_folder_saves_no_reference_patch(
    task: LocalTask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(task, "task_folder", lambda: None)
    save_reference_patch(task, tmp_path)
    assert not (tmp_path / "reference.patch").exists()


def test_the_result_is_replaced_not_rewritten(task: LocalTask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # In the container, root writes result.json: the host user cannot write to it, only replace it.
    monkeypatch.chdir(tmp_path)
    result = tmp_path / "result.json"
    _ = result.write_text(
        '{"patch_result": {"build_success": true}, '
        '"runtime_result": {"agent_duration": 1, "agent_timeout": false, "evaluator_timeout": false}}'
    )
    result.chmod(0o444)
    config = RunConfig(agent="dummy", model="none", mode="sandbox", timeout=60, difficulty=2)

    record_results(task, config, 0.0, result)

    assert '"agent":"dummy"' in result.read_text()
    assert (tmp_path / "summary.json").is_file()


def record_with_plugin_report(task: LocalTask, run_dir: Path, report: str | None) -> dict[str, Any]:
    result = run_dir / "result.json"
    _ = result.write_text(
        '{"patch_result": {"build_success": true}, '
        '"runtime_result": {"agent_duration": 1, "agent_timeout": false, "evaluator_timeout": false}}'
    )
    if report is not None:
        (run_dir / "archive" / "plugins").mkdir(parents=True)
        _ = (run_dir / "archive" / "plugins" / "results.json").write_text(report)
    config = RunConfig(agent="dummy", model="none", mode="sandbox", timeout=60, difficulty=2)
    record_results(task, config, 0.0, result)
    return json.loads((run_dir / "summary.json").read_text())


def test_the_summary_records_a_skipped_plugin_with_its_reason(task: LocalTask, tmp_path: Path) -> None:
    report = json.dumps(
        [
            {
                "name": "oracle",
                "hook": "after-grading",
                "status": "skipped",
                "exit_code": 0,
                "duration_seconds": 0.05,
                "started": True,
                "reason": "No LLM configured (SSE_API_KEY, SSE_BASE_URL unset)",
            }
        ]
    )
    (tmp_path / "archive").mkdir()

    summary = record_with_plugin_report(task, tmp_path, report)

    [plugin] = summary["plugin_results"]
    assert plugin["name"] == "oracle"
    assert plugin["status"] == "skipped"
    assert plugin["reason"] == "No LLM configured (SSE_API_KEY, SSE_BASE_URL unset)"


@pytest.mark.parametrize("report", [None, "not json", '{"name": "oracle"}'])
def test_a_missing_or_unreadable_plugin_report_leaves_the_summary_without_plugin_results(
    task: LocalTask, tmp_path: Path, report: str | None
) -> None:
    (tmp_path / "archive").mkdir()

    assert record_with_plugin_report(task, tmp_path, report)["plugin_results"] == []


def test_both_sidecar_containers_mount_the_results(
    task: LocalTask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, docker: FakeDocker
) -> None:
    monkeypatch.chdir(tmp_path)
    runner = BenchmarkSidecarRunner(NoModel(), Agent("dummy", task_name=TASK), task, 60, 2, run_id="r1")
    runner.images = Images(agent="registry.test/agent", environment="registry.test/environment")

    runner.run()

    runs = docker.runs()
    assert len(runs) == 2
    run_dir = tmp_path / "results" / TASK / "none" / "dummy" / "r1"
    for cmd in runs:
        assert f"{run_dir}:{RESULTS_PATH}" in options(cmd, "-v")
        assert f"{run_dir / 'archive'}:{ARCHIVE_PATH}" in options(cmd, "-v")
    assert (run_dir / "reference.patch").read_text() == "fix\n"


class Containers:
    """The task containers of a run, each writing the grade the test chose for it."""

    def __init__(self, *grades: bool) -> None:
        self.grades = list(grades)
        self.finished = 0

    def __call__(self, cmd: list[str]) -> int:
        [mount] = [v for v in options(cmd, "-v") if v.endswith(f":{RESULTS_PATH}")]
        run_dir = Path(mount.removesuffix(f":{RESULTS_PATH}"))
        self.finished += 1
        _ = (run_dir / "final.patch").write_text(f"patch {self.finished}\n")
        passed = self.grades[self.finished - 1]
        grade: dict[str, Any] = {
            "patch_result": {"build_success": True, "pov_passed": int(passed), "pov_total": 1},
            "runtime_result": {"agent_duration": 1, "agent_timeout": False, "evaluator_timeout": False},
        }
        _ = (run_dir / "result.json").write_text(json.dumps(grade))
        return 0


def run_twice(
    task: LocalTask,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    make_runner: Callable[..., object],
    docker: FakeDocker,
) -> Path:
    monkeypatch.chdir(tmp_path)
    docker.on_run = Containers(False, True)
    for run_id in ("first", "second"):
        make_runner(run_id).run()  # pyright: ignore[reportAttributeAccessIssue]
    return tmp_path / "results" / TASK / "none" / "dummy"


def sandbox(task: LocalTask, run_id: str | None = None) -> BenchmarkSandboxRunner:
    runner = BenchmarkSandboxRunner(NoModel(), Agent("dummy", task_name=TASK), task, 60, 2, run_id=run_id)
    runner.images = Images(agent="registry.test/image")
    return runner


def sidecar(task: LocalTask, run_id: str | None = None) -> BenchmarkSidecarRunner:
    runner = BenchmarkSidecarRunner(NoModel(), Agent("dummy", task_name=TASK), task, 60, 2, run_id=run_id)
    runner.images = Images(agent="registry.test/agent", environment="registry.test/environment")
    return runner


@pytest.mark.parametrize("make_runner", [sandbox, sidecar])
def test_two_runs_of_the_same_task_model_and_agent_both_keep_their_results(
    make_runner: Callable[..., BenchmarkSandboxRunner | BenchmarkSidecarRunner],
    task: LocalTask,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    docker: FakeDocker,
) -> None:
    group = run_twice(task, monkeypatch, tmp_path, lambda run_id: make_runner(task, run_id), docker)

    assert sorted(p.name for p in group.iterdir()) == ["first", LATEST, "second"]
    for run_id, passed, patch in (("first", 0, "patch 1\n"), ("second", 1, "patch 2\n")):
        run = group / run_id
        assert json.loads((run / "result.json").read_text())["patch_result"]["pov_passed"] == passed
        assert (run / "final.patch").read_text() == patch
        assert (run / "reference.patch").read_text() == "fix\n"
        summary = json.loads((run / "summary.json").read_text())
        assert summary["run_id"] == run_id
        assert summary["patch_result"]["pov_passed"] == passed
        assert summary["started_at"].endswith("Z")
    first, second = (json.loads((group / r / "summary.json").read_text())["started_at"] for r in ("first", "second"))
    assert first <= second


@pytest.mark.parametrize("make_runner", [sandbox, sidecar])
def test_latest_points_at_the_newest_run_and_can_be_replaced_by_the_host_user(
    make_runner: Callable[..., BenchmarkSandboxRunner | BenchmarkSidecarRunner],
    task: LocalTask,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    docker: FakeDocker,
) -> None:
    group = run_twice(task, monkeypatch, tmp_path, lambda run_id: make_runner(task, run_id), docker)

    assert (group / LATEST).is_symlink()
    assert (group / LATEST).readlink() == Path("second")
    assert json.loads((group / LATEST / "result.json").read_text())["patch_result"]["pov_passed"] == 1


def test_a_second_run_with_the_same_id_is_refused_and_leaves_the_first_alone(
    task: LocalTask, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, docker: FakeDocker
) -> None:
    monkeypatch.chdir(tmp_path)
    docker.on_run = Containers(True, True)
    sandbox(task, "same").run()
    before = (tmp_path / "results" / TASK / "none" / "dummy" / "same" / "summary.json").read_text()

    with pytest.raises(UserError, match="already has results"):
        sandbox(task, "same").run()

    assert (tmp_path / "results" / TASK / "none" / "dummy" / "same" / "summary.json").read_text() == before
