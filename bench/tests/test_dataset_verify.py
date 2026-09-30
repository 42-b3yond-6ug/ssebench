import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ssebench.cli import main
from ssebench.dataset import verify
from ssebench.dataset.generate import MANIFEST, build_manifest, render_manifest
from ssebench.runner.result import PatchResult, PerTaskEvaluationResult, RunConfig, RuntimeResult
from ssebench.tasks.manifest import Check
from ssebench.tasks.metadata import TaskMetadata

MakeTask = Callable[..., Path]
TaskConfig = Callable[[str], dict[str, Any]]
ALL_CHECKS: list[Check] = ["build", "poc", "function_test", "intent_test"]


def run_cli(*argv: str) -> int:
    with pytest.raises(SystemExit) as exit_info:
        main(list(argv))
    code = exit_info.value.code
    assert isinstance(code, int)
    return code


def grade(**fields: object) -> PatchResult:
    return PatchResult.model_validate(
        {"build_success": True, "pov_passed": 1, "pov_total": 1, "func_test_success": True}
        | {"intent_test_success": True}
        | fields
    )


# Judging a run


def test_reference_that_passes_every_check() -> None:
    report = verify.judge(verify.REFERENCE, grade(), ALL_CHECKS, pocs=1)

    assert report.cells == dict.fromkeys(ALL_CHECKS, "ok")
    assert report.failures == []


def test_reference_whose_tests_fail() -> None:
    report = verify.judge(verify.REFERENCE, grade(func_test_success=False, pov_passed=0), ALL_CHECKS, pocs=1)

    assert report.cells == {"build": "ok", "poc": "FAIL", "function_test": "FAIL", "intent_test": "ok"}
    assert report.failures == [
        "1 of 1 PoCs still trigger the bug with the fix",
        "the functional tests fail",
    ]


def test_dummy_that_still_triggers_the_bug() -> None:
    report = verify.judge(verify.DUMMY, grade(pov_passed=0, intent_test_success=False), ALL_CHECKS, pocs=1)

    assert report.cells == dict.fromkeys(ALL_CHECKS, "ok")
    assert report.failures == []
    assert report.warnings == []


def test_dummy_whose_poc_passes_fails() -> None:
    report = verify.judge(verify.DUMMY, grade(intent_test_success=False), ALL_CHECKS, pocs=1)

    assert report.cells["poc"] == "FAIL"
    assert report.failures == ["1 of 1 PoCs do not trigger the bug without the fix"]


def test_dummy_whose_intent_tests_pass_is_a_warning() -> None:
    report = verify.judge(verify.DUMMY, grade(pov_passed=0), ALL_CHECKS, pocs=1)

    assert report.cells["intent_test"] == "warn"
    assert report.failures == []
    assert report.warnings == ["the intent tests pass without the fix, so they do not check it"]


def test_a_failed_build_skips_the_other_checks() -> None:
    result = PatchResult(build_success=False, func_test_success=False, intent_test_success=False)

    report = verify.judge(verify.DUMMY, result, ALL_CHECKS, pocs=1)

    assert report.cells == {"build": "FAIL", "poc": "skip", "function_test": "skip", "intent_test": "skip"}
    assert report.failures == ["the project does not build"]


def test_every_poc_must_run() -> None:
    report = verify.judge(verify.REFERENCE, grade(pov_passed=1, pov_total=1), ALL_CHECKS, pocs=2)

    assert report.failures == ["1 of 2 PoCs ran"]


def test_missing_or_ungraded_results_are_errors() -> None:
    missing = verify.judge(verify.REFERENCE, None, ["build", "function_test"], pocs=0)
    ungraded = verify.judge(verify.REFERENCE, PatchResult(error_msg="Timeout (60s)"), ["build"], pocs=0)

    assert missing.cells == {"build": "error", "function_test": "error"}
    assert missing.failures == ["the run wrote no result; see its log"]
    assert ungraded.failures == ["not graded: Timeout (60s)"]


def test_checks_the_task_does_not_have_are_not_judged() -> None:
    report = verify.judge(verify.REFERENCE, grade(pov_passed=None, pov_total=None), ["build", "function_test"], 0)

    assert report.cells == {"build": "ok", "function_test": "ok"}


# Running


def test_only_the_dummy_run_names_a_model(tmp_path: Path) -> None:
    opts = verify.Options(dataset=tmp_path / "pilot", output=tmp_path / "out", model="some-model")

    reference = verify.run_command(opts, "demo-1", verify.REFERENCE)
    dummy = verify.run_command(opts, "demo-1", verify.DUMMY)

    assert "--model" not in reference
    assert dummy[dummy.index("--model") + 1] == "some-model"
    assert verify.result_path(opts, "demo-1", verify.REFERENCE) == (
        tmp_path / "out" / "runs" / "results" / "demo-1-reference-none.json"
    )


def run_summary(task_config: TaskConfig, patch_result: dict[str, object]) -> str:
    """The summary `ssebench run` writes for a run with this grade."""
    return PerTaskEvaluationResult(
        task=TaskMetadata.model_validate(task_config("demo-1")),
        config=RunConfig(agent="dummy", model="some-model", mode="sandbox", timeout=60, difficulty=2),
        patch_result=PatchResult.model_validate(patch_result),
        runtime_result=RuntimeResult(agent_duration=0, agent_timeout=False, evaluator_timeout=False),
        spend=0,
    ).model_dump_json()


def test_read_result(tmp_path: Path, task_config: TaskConfig) -> None:
    path = tmp_path / "result.json"
    _ = path.write_text(run_summary(task_config, {"build_success": True}))

    result = verify.read_result(path)

    assert result is not None and result.build_success is True
    _ = path.write_text("")
    assert verify.read_result(path) is None
    assert verify.read_result(tmp_path / "missing.json") is None


# Selecting tasks


def git(repo: Path, *args: str) -> None:
    _ = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def commit(repo: Path, message: str) -> None:
    identity = ("-c", "user.name=t", "-c", "user.email=t@example.org", "-c", "commit.gpgsign=false")
    git(repo, *identity, "commit", "--quiet", "-m", message)


@pytest.fixture
def repo(tmp_path: Path, make_task: MakeTask) -> Path:
    """A repository with a dataset of three tasks, its manifest and a base image folder, committed."""
    root = tmp_path / "repo"
    dataset = root / "datasets" / "demo"
    for task in ("demo-1", "demo-2", "demo-3"):
        _ = make_task(dataset, task)
    _ = (dataset / MANIFEST).write_text(render_manifest(build_manifest(dataset)))
    base = root / "images" / "base-images" / "generic-c" / "Dockerfile"
    base.parent.mkdir(parents=True)
    _ = base.write_text("FROM scratch\n")
    git(root, "init", "--quiet")
    git(root, "add", "--all")
    commit(root, "init")
    git(root, "branch", "base")
    return root


def changed(repo: Path) -> list[str]:
    report = verify.load_tasks(repo / "datasets" / "demo")
    return [t.id for t in verify.changed_tasks(report, "base")]


def test_nothing_changed(repo: Path) -> None:
    assert changed(repo) == []


def test_changed_and_new_tasks(repo: Path, make_task: MakeTask) -> None:
    _ = (repo / "datasets" / "demo" / "demo-2" / "sse" / "run.sh").write_text('#!/bin/sh\n./demo --fixed "$1"\n')
    _ = make_task(repo / "datasets" / "demo", "demo-4")

    assert changed(repo) == ["demo-2", "demo-4"]


def test_a_changed_base_image_selects_its_tasks(repo: Path) -> None:
    _ = (repo / "images" / "base-images" / "generic-c" / "Dockerfile").write_text("FROM busybox\n")

    assert changed(repo) == ["demo-1", "demo-2", "demo-3"]


def test_every_task_without_a_manifest_at_the_base(repo: Path) -> None:
    git(repo, "rm", "--quiet", "datasets/demo/manifest.json")
    commit(repo, "rm")
    git(repo, "branch", "--force", "base")
    _ = (repo / "datasets" / "demo" / MANIFEST).write_text("{}")

    assert changed(repo) == ["demo-1", "demo-2", "demo-3"]


def test_base_dir_name() -> None:
    assert verify.base_dir_name("base-generic-go:1.0.0") == "generic-go"
    assert verify.base_dir_name("base-generic-c@sha256:abc") == "generic-c"


def test_unknown_tasks_are_rejected(repo: Path) -> None:
    report = verify.load_tasks(repo / "datasets" / "demo")

    with pytest.raises(verify.SelectionError, match="nope"):
        _ = verify.select_tasks(report, ["demo-1", "nope"])
    assert [t.id for t in verify.select_tasks(report, [])] == ["demo-1", "demo-2", "demo-3"]


def test_cli_lists_tasks(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = run_cli("dataset", "verify", "--dir", str(repo / "datasets" / "demo"), "--list", "demo-3")

    assert code == 0
    assert json.loads(capsys.readouterr().out) == [{"task": "demo-3", "base": "base-generic-c:1.0.0"}]


# Results


def verdict(task: str, dummy: PatchResult) -> verify.TaskVerdict:
    v = verify.TaskVerdict(task=task, base="base-generic-c:1.0.0", checks=ALL_CHECKS, pocs=1)
    v.runs[verify.REFERENCE] = verify.judge(verify.REFERENCE, grade(), ALL_CHECKS, 1)
    v.runs[verify.DUMMY] = verify.judge(verify.DUMMY, dummy, ALL_CHECKS, 1)
    for run in v.runs.values():
        run.seconds = 61
        run.log = f"logs/{task}.{run.agent}.log"
    return v


def test_runs_that_graded_different_images_do_not_verify_a_task() -> None:
    v = verdict("demo-1", grade(pov_passed=0, intent_test_success=False))
    v.runs[verify.REFERENCE].image = "sha256:aa"
    v.runs[verify.DUMMY].image = "sha256:aa"
    assert v.ok

    v.runs[verify.DUMMY].image = "sha256:bb"

    assert not v.ok
    assert v.failures == ["the runs graded different case images, so no single image has been verified"]


def test_summary(tmp_path: Path) -> None:
    good = verdict("demo-1", grade(pov_passed=0, intent_test_success=False))
    bad = verdict("demo-2", grade(intent_test_success=True))

    markdown = verify.summary_markdown([good, bad], "Demo")
    data = verify.summary_json([good, bad], {"dataset": "demo"})

    assert "1 of 2 tasks grade as expected." in markdown
    assert "| demo-1 | base-generic-c:1.0.0 | ok | ok | ok | ok | ok | ok | ok | ok | 2m02s | pass |" in markdown
    assert (
        "| demo-2 | base-generic-c:1.0.0 | ok | ok | ok | ok | ok | FAIL | ok | warn | 2m02s | **FAIL** |" in markdown
    )
    assert "- **demo-2**: dummy: 1 of 1 PoCs do not trigger the bug without the fix" in markdown
    assert data["passed"] == 1 and data["failed"] == ["demo-2"] and data["dataset"] == "demo"


def test_verdicts_round_trip(tmp_path: Path) -> None:
    original = verdict("demo-1", grade(pov_passed=0, intent_test_success=False))

    _ = verify.write_verdict(tmp_path, original)
    [read] = verify.read_verdicts(tmp_path)

    assert read.to_json() == original.to_json()
    assert read.ok


def test_cli_summarizes_results(repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "out"
    _ = verify.write_verdict(output, verdict("demo-1", grade(pov_passed=0, intent_test_success=False)))
    _ = verify.write_verdict(output, verdict("gone", grade(pov_passed=0, intent_test_success=False)))
    args = ("dataset", "verify", "--dir", str(repo / "datasets" / "demo"), "--output", str(output), "--summarize")

    assert run_cli(*args) == 0
    summary = json.loads((output / "summary.json").read_text())
    assert [t["task"] for t in summary["tasks"]] == ["demo-1"]
    assert "1 of 1 tasks grade as expected." in capsys.readouterr().out

    _ = verify.write_verdict(output, verdict("demo-2", grade()))
    assert run_cli(*args) == 1


def test_a_named_task_without_a_result_fails_the_summary(repo: Path, tmp_path: Path) -> None:
    output = tmp_path / "out"
    _ = verify.write_verdict(output, verdict("demo-1", grade(pov_passed=0, intent_test_success=False)))
    args = ("dataset", "verify", "--dir", str(repo / "datasets" / "demo"), "--output", str(output), "--summarize")

    assert run_cli(*args, "demo-1", "demo-3") == 1
    summary = json.loads((output / "summary.json").read_text())
    assert summary["failed"] == ["demo-3"]
    assert summary["tasks"][1]["failures"] == [
        "reference: no result, the verification did not finish",
        "dummy: no result, the verification did not finish",
    ]


def test_tasks_of_one_project_are_spread_out(tmp_path: Path, make_task: MakeTask) -> None:
    dataset = tmp_path / "demo"
    for task, project in (("a-1", "a"), ("a-2", "a"), ("a-3", "a"), ("b-1", "b"), ("c-1", "c")):
        _ = make_task(dataset, task, {"project": project})
    tasks = verify.load_tasks(dataset).tasks

    assert [t.id for t in verify.spread(tasks)] == ["a-1", "b-1", "c-1", "a-2", "a-3"]


def test_a_run_without_a_result_is_retried(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, task_config: TaskConfig
) -> None:
    report = verify.load_tasks(repo / "datasets" / "demo")
    [task] = verify.select_tasks(report, ["demo-1"])
    opts = verify.Options(dataset=repo / "datasets" / "demo", output=tmp_path / "out", retries=1)
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if cmd[0] == "docker":
            return subprocess.CompletedProcess(cmd, 0, "sha256:aa\n", "")
        calls.append(cmd)
        if len(calls) == 2:
            path = verify.result_path(opts, "demo-1", verify.DUMMY)
            path.parent.mkdir(parents=True, exist_ok=True)
            result = {"build_success": True, "pov_passed": 0, "pov_total": 1, "func_test_success": True}
            _ = path.write_text(run_summary(task_config, result))
        return subprocess.CompletedProcess(cmd, 1 if len(calls) == 1 else 0)

    monkeypatch.setattr(verify.subprocess, "run", fake_run)
    run = verify.run_agent(opts, task, verify.DUMMY)

    assert len(calls) == 2
    assert run.attempts == 2 and run.exit_code == 0
    assert run.cells["poc"] == "ok"
    assert run.image == "sha256:aa"


def test_the_image_of_a_run_without_one_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(verify.subprocess, "run", lambda cmd, **_: subprocess.CompletedProcess(cmd, 1, "", "no image"))

    assert verify.image_id("registry.test/case/demo/demo-1") is None
