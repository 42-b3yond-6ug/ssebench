"""Grade a dataset's tasks with the reference and dummy agents, and check that each grades as a sound task does.

A sound task grades the reference agent's patch, the upstream fix, as passing every check the task
has. It grades the dummy agent's empty patch as a project that builds and passes its own tests but
still triggers every proof of concept; the intent tests should fail too, or they do not check the fix.
Each run is a real `ssebench run` in a subprocess, so the check covers the case image, the tool
layer and the grader as well as the task.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from ssebench import paths
from ssebench.models import NO_MODEL
from ssebench.pipe import REGISTRY
from ssebench.runner.result import PatchResult, PerTaskEvaluationResult
from ssebench.runner.runner import summary_path
from ssebench.tasks.manifest import Check, case_image_name, task_files

from .generate import MANIFEST, checks
from .validate import DatasetReport, TaskReport, validate_dataset

REFERENCE = "reference"
DUMMY = "dummy"
AGENTS = (REFERENCE, DUMMY)

# The dummy agent makes no model calls, but a run needs a model that the proxy serves.
DEFAULT_DUMMY_MODEL = "claude-sonnet-4-6"
# Base images are built from images/base-images/<name>/ and named base-<name>.
BASE_IMAGES_DIR = "images/base-images"

Cell = Literal["ok", "FAIL", "warn", "skip", "error", "-"]
CHECKS: tuple[Check, ...] = ("build", "poc", "function_test", "intent_test")


@dataclass
class RunReport:
    """One agent's run of a task and how it compares with what a sound task gives."""

    agent: str
    exit_code: int
    seconds: float
    log: str
    result: dict[str, Any] | None = None
    attempts: int = 1
    image: str | None = None
    """ID of the local case image that the run graded; the image to publish must be this one."""
    cells: dict[str, Cell] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class TaskVerdict:
    task: str
    base: str
    checks: list[Check]
    pocs: int
    runs: dict[str, RunReport] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def failures(self) -> list[str]:
        missing = [f"{agent}: no result, the verification did not finish" for agent in AGENTS if agent not in self.runs]
        failures = missing + [f"{run.agent}: {f}" for run in self.runs.values() for f in run.failures]
        if len({run.image for run in self.runs.values() if run.image}) > 1:
            failures.append("the runs graded different case images, so no single image has been verified")
        return failures

    @property
    def warnings(self) -> list[str]:
        return [f"{run.agent}: {w}" for run in self.runs.values() for w in run.warnings]

    @property
    def seconds(self) -> float:
        return sum(run.seconds for run in self.runs.values())

    def to_json(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "base": self.base,
            "checks": self.checks,
            "pocs": self.pocs,
            "ok": self.ok,
            "seconds": round(self.seconds, 1),
            "failures": self.failures,
            "warnings": self.warnings,
            "runs": {agent: asdict(run) for agent, run in self.runs.items()},
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> TaskVerdict:
        verdict = cls(task=data["task"], base=data["base"], checks=data["checks"], pocs=data["pocs"])
        verdict.runs = {agent: RunReport(**run) for agent, run in data["runs"].items()}
        return verdict


# Judging one run


def judge(agent: str, result: PatchResult | None, task_checks: Sequence[Check], pocs: int) -> RunReport:
    """Compare a run's grade with what a sound task gives for the agent; timing and log are left empty."""
    report = RunReport(agent=agent, exit_code=0, seconds=0.0, log="")
    if result is None:
        report.failures.append("the run wrote no result; see its log")
        report.cells = dict.fromkeys(task_checks, "error")
        return report
    report.result = result.model_dump(mode="json")
    graded = (result.build_success, result.pov_total, result.func_test_success, result.intent_test_success)
    if all(v is None for v in graded):
        report.failures.append(f"not graded: {result.error_msg or 'no check ran'}")
        report.cells = dict.fromkeys(task_checks, "error")
        return report

    expect_fix = agent == REFERENCE
    for check in task_checks:
        cell, problem = _judge_check(check, result, expect_fix, pocs)
        report.cells[check] = cell
        if problem is not None:
            (report.warnings if cell == "warn" else report.failures).append(problem)
    return report


def _judge_check(check: Check, r: PatchResult, expect_fix: bool, pocs: int) -> tuple[Cell, str | None]:
    """The cell of one check, and what is wrong with it, if anything."""
    if check == "build":
        return ("ok", None) if r.build_success else ("FAIL", "the project does not build")
    if not r.build_success:
        return "skip", None
    match check:
        case "poc":
            if r.pov_total is None or r.pov_passed is None:
                return "FAIL", "the PoCs did not run"
            if r.pov_total != pocs:
                return "FAIL", f"{r.pov_total} of {pocs} PoCs ran"
            if expect_fix:
                if r.pov_passed == r.pov_total:
                    return "ok", None
                return "FAIL", f"{r.pov_total - r.pov_passed} of {r.pov_total} PoCs still trigger the bug with the fix"
            if r.pov_passed == 0:
                return "ok", None
            return "FAIL", f"{r.pov_passed} of {r.pov_total} PoCs do not trigger the bug without the fix"
        case "function_test":
            if r.func_test_success is None:
                return "FAIL", "the functional tests did not run"
            return ("ok", None) if r.func_test_success else ("FAIL", "the functional tests fail")
        case "intent_test":
            if r.intent_test_success is None:
                return "FAIL", "the intent tests did not run"
            if expect_fix:
                return ("ok", None) if r.intent_test_success else ("FAIL", "the intent tests fail")
            if r.intent_test_success:
                return "warn", "the intent tests pass without the fix, so they do not check it"
            return "ok", None
        case _:
            return "-", None


# Running


@dataclass(frozen=True)
class Options:
    dataset: Path
    output: Path
    model: str = DEFAULT_DUMMY_MODEL
    difficulty: int = 2
    timeout: int = 3600
    egress: str = "restricted"
    # Runs that end without a result, such as a case image build that lost the network, are retried.
    retries: int = 0


def run_command(opts: Options, task: str, agent: str) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "ssebench",
        "run",
        "--local",
        str(opts.dataset),
        "--task",
        task,
        "--agent",
        agent,
        "--difficulty",
        str(opts.difficulty),
        "--timeout",
        str(opts.timeout),
        "--egress",
        opts.egress,
    ]
    if agent != REFERENCE:
        cmd += ["--model", opts.model]
    return cmd


def result_path(opts: Options, task: str, agent: str) -> Path:
    """The summary of the run, which `ssebench run`, started in the runs directory, writes when it ends."""
    model = NO_MODEL if agent == REFERENCE else opts.model
    return runs_dir(opts.output) / summary_path(task, agent, model)


def runs_dir(output: Path) -> Path:
    return output / "runs"


def read_result(path: Path) -> PatchResult | None:
    try:
        text = path.read_text().strip()
    except OSError:
        return None
    if not text:
        return None
    try:
        return PerTaskEvaluationResult.model_validate_json(text).patch_result
    except ValidationError:
        return None


def case_image(dataset: Path, task: str) -> str:
    """The name of the case image that `ssebench run --local DATASET` builds for a task."""
    return f"{REGISTRY}/{case_image_name(dataset.resolve().name, task)}"


def image_id(image: str) -> str | None:
    """The ID of a local image, or None if there is none."""
    proc = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", image], capture_output=True, text=True)
    return (proc.stdout.strip() or None) if proc.returncode == 0 else None


def run_agent(opts: Options, task: TaskReport, agent: str) -> RunReport:
    result_file = result_path(opts, task.id, agent)
    result_file.unlink(missing_ok=True)
    log = opts.output / "logs" / f"{task.id}.{agent}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    runs = runs_dir(opts.output)
    runs.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, paths.HOME_ENV: str(paths.home())}

    start = time.monotonic()
    attempts = 0
    with log.open("w") as out:
        while True:
            attempts += 1
            _ = out.write(f"=== {agent} run of {task.id}, attempt {attempts}\n")
            out.flush()
            proc = subprocess.run(
                run_command(opts, task.id, agent), cwd=runs, env=env, stdout=out, stderr=subprocess.STDOUT, check=False
            )
            result = read_result(result_file)
            if result is not None or attempts > opts.retries:
                break
    seconds = time.monotonic() - start

    assert task.metadata is not None
    report = judge(agent, result, checks(task.metadata), len(task.metadata.files.poc or []))
    report.attempts = attempts
    report.image = image_id(case_image(opts.dataset, task.id))
    report.exit_code = proc.returncode
    report.seconds = round(seconds, 1)
    report.log = log.relative_to(opts.output).as_posix()
    return report


def verify_task(opts: Options, task: TaskReport) -> TaskVerdict:
    assert task.metadata is not None
    verdict = TaskVerdict(
        task=task.id, base=task.base, checks=checks(task.metadata), pocs=len(task.metadata.files.poc or [])
    )
    for agent in AGENTS:
        verdict.runs[agent] = run_agent(opts, task, agent)
    write_verdict(opts.output, verdict)
    return verdict


def spread(tasks: Sequence[TaskReport]) -> list[TaskReport]:
    """Order tasks round-robin by project.

    Tasks of one project build and test the same code, often with every core, so running them
    side by side overloads the host and makes timing-sensitive tests fail.
    """
    groups: dict[str, list[TaskReport]] = {}
    for task in tasks:
        groups.setdefault(task.metadata.project if task.metadata else task.id, []).append(task)
    queues = sorted(groups.values(), key=len, reverse=True)
    ordered: list[TaskReport] = []
    for i in range(len(queues[0]) if queues else 0):
        ordered += [queue[i] for queue in queues if i < len(queue)]
    return ordered


def verify(
    opts: Options, tasks: Sequence[TaskReport], jobs: int, progress: Callable[[str], None] = print
) -> list[TaskVerdict]:
    """Verify the tasks, `jobs` at a time; each task's reference and dummy runs are sequential."""
    verdicts: list[TaskVerdict] = []
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = {pool.submit(verify_task, opts, task): task for task in spread(tasks)}
        for done, future in enumerate(as_completed(futures), start=1):
            verdict = future.result()
            verdicts.append(verdict)
            status = "ok" if verdict.ok else "FAIL"
            detail = f"  {verdict.failures[0]}" if verdict.failures else ""
            progress(f"[{done}/{len(tasks)}] {status:4} {verdict.task} ({duration(verdict.seconds)}){detail}")
    return sorted(verdicts, key=lambda v: v.task)


# Selecting tasks


class SelectionError(Exception):
    pass


def load_tasks(dataset: Path) -> DatasetReport:
    report = validate_dataset(dataset)
    if not report.ok:
        raise SelectionError(f"{dataset} has invalid tasks; run `ssebench dataset validate`:\n{report.format_errors()}")
    return report


def select_tasks(report: DatasetReport, names: Iterable[str]) -> list[TaskReport]:
    by_id = {t.id: t for t in report.tasks}
    wanted = list(dict.fromkeys(names))
    unknown = [n for n in wanted if n not in by_id]
    if unknown:
        raise SelectionError(f"no such task in {report.path}: {', '.join(unknown)}")
    return [by_id[n] for n in wanted] if wanted else list(report.tasks)


def base_dir_name(base: str) -> str:
    """The folder under images/base-images of a base image such as base-generic-go:1.0.0."""
    return base.partition(":")[0].partition("@")[0].removeprefix("base-")


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise SelectionError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def changed_tasks(report: DatasetReport, since: str) -> list[TaskReport]:
    """The tasks that differ from the dataset at the merge base of `since` and HEAD.

    A task counts as changed when it is new, when a file in its folder changed (the `files` of
    the manifest at that commit), or when a file of its base image under images/base-images did.
    """
    dataset = report.path.resolve()
    repo = Path(git(dataset, "rev-parse", "--show-toplevel").strip())
    base = git(repo, "merge-base", since, "HEAD").strip()
    manifest = (dataset / MANIFEST).relative_to(repo).as_posix()
    try:
        old = json.loads(git(repo, "show", f"{base}:{manifest}"))
        old_tasks: dict[str, dict[str, Any]] = {t["id"]: t for t in old.get("tasks", [])}
    except SelectionError:
        return list(report.tasks)

    changed_bases = {
        parts[2]
        for line in git(repo, "diff", "--name-only", base, "--", BASE_IMAGES_DIR).splitlines()
        if len(parts := line.split("/")) > 3
    }
    selected: list[TaskReport] = []
    for task in report.tasks:
        previous = old_tasks.get(task.id)
        if (
            previous is None
            or previous.get("files") != task_files(task.path)
            or previous.get("base") != task.base
            or base_dir_name(task.base) in changed_bases
        ):
            selected.append(task)
    return selected


# Results


def write_verdict(output: Path, verdict: TaskVerdict) -> Path:
    path = output / "tasks" / f"{verdict.task}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(verdict.to_json(), indent=2) + "\n")
    return path


def read_verdict(output: Path, task: str) -> TaskVerdict | None:
    """The result of one task in `output`, or None if it has none."""
    try:
        return TaskVerdict.from_json(json.loads((output / "tasks" / f"{task}.json").read_text()))
    except OSError:
        return None


def read_verdicts(output: Path) -> list[TaskVerdict]:
    files = sorted((output / "tasks").glob("*.json"))
    return sorted((TaskVerdict.from_json(json.loads(p.read_text())) for p in files), key=lambda v: v.task)


def collect_verdicts(output: Path, tasks: Sequence[TaskReport], complete: bool) -> list[TaskVerdict]:
    """The results in `output` of these tasks. With `complete`, a task without one counts as failed."""
    found = {v.task: v for v in read_verdicts(output)}
    verdicts: list[TaskVerdict] = []
    for task in tasks:
        if task.id in found:
            verdicts.append(found[task.id])
        elif complete:
            assert task.metadata is not None
            verdicts.append(TaskVerdict(task.id, task.base, checks(task.metadata), len(task.metadata.files.poc or [])))
    return verdicts


def duration(seconds: float) -> str:
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes}m{secs:02d}s"


COLUMNS: tuple[tuple[str, str, Check], ...] = (
    ("Ref build", REFERENCE, "build"),
    ("Ref PoC", REFERENCE, "poc"),
    ("Ref tests", REFERENCE, "function_test"),
    ("Ref intent", REFERENCE, "intent_test"),
    ("Dummy build", DUMMY, "build"),
    ("Dummy PoC", DUMMY, "poc"),
    ("Dummy tests", DUMMY, "function_test"),
    ("Dummy intent", DUMMY, "intent_test"),
)

LEGEND = """\
Each task is graded twice. The reference agent applies the upstream fix: every check must pass.
The dummy agent changes nothing: the project must build and pass its functional tests while every
PoC still triggers the bug. The dummy's intent tests should fail; `warn` marks intent tests that
pass without the fix. `-` is a check the task does not have; `skip` did not run because the build
failed; `error` means the run was not graded."""


def cell(verdict: TaskVerdict, agent: str, check: Check) -> str:
    run = verdict.runs.get(agent)
    if run is None:
        return "error"
    return run.cells.get(check, "-")


def summary_markdown(verdicts: Sequence[TaskVerdict], title: str) -> str:
    passed = sum(v.ok for v in verdicts)
    lines = [
        f"## {title}",
        "",
        f"{passed} of {len(verdicts)} tasks grade as expected.",
        "",
        LEGEND,
        "",
        "| Task | Base | " + " | ".join(name for name, _, _ in COLUMNS) + " | Time | Result |",
        "|---|---|" + "---|" * len(COLUMNS) + "---|---|",
    ]
    for v in verdicts:
        cells = [cell(v, agent, check) for _, agent, check in COLUMNS]
        result = "pass" if v.ok else "**FAIL**"
        lines.append(f"| {v.task} | {v.base} | " + " | ".join(cells) + f" | {duration(v.seconds)} | {result} |")
    failed = [v for v in verdicts if not v.ok]
    if failed:
        lines += ["", "### Failures", ""]
        for v in failed:
            logs = ", ".join(f"`{run.log}`" for run in v.runs.values() if run.log)
            lines.append(
                f"- **{v.task}**: " + "; ".join(v.failures or ["incomplete"]) + (f" (logs: {logs})" if logs else "")
            )
    warned = [v for v in verdicts if v.warnings]
    if warned:
        lines += ["", "### Warnings", ""]
        lines += [f"- **{v.task}**: " + "; ".join(v.warnings) for v in warned]
    return "\n".join(lines) + "\n"


def summary_json(verdicts: Sequence[TaskVerdict], meta: dict[str, Any]) -> dict[str, Any]:
    return {
        **meta,
        "total": len(verdicts),
        "passed": sum(v.ok for v in verdicts),
        "failed": [v.task for v in verdicts if not v.ok],
        "tasks": [v.to_json() for v in verdicts],
    }


def write_summary(output: Path, verdicts: Sequence[TaskVerdict], title: str, meta: dict[str, Any]) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    markdown = output / "summary.md"
    _ = markdown.write_text(summary_markdown(verdicts, title))
    _ = (output / "summary.json").write_text(json.dumps(summary_json(verdicts, meta), indent=2) + "\n")
    return markdown
