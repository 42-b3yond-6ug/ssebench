"""`ssebench runs`: the JSON interface that the web UI drives, on any backend, and the finished runs in results/."""

import json
import os
import subprocess
from collections.abc import Iterator, Mapping
from pathlib import Path, PurePosixPath
from typing import override

import pytest

from ssebench.backends import (
    RESULTS_LABEL,
    RUN_ID_LABEL,
    TASK_LABEL,
    WEBUI_LABEL,
    Backend,
    BackendError,
    DockerBackend,
    DockerRun,
    ImageRequest,
    Images,
    RunHandle,
    RunInfo,
    RunSpec,
)
from ssebench.cli import runs
from ssebench.cli.cli import main


class ClusterBackend(Backend):
    """A backend that has runs but no container CLI: it reaches them through a service and cannot exec."""

    name = "cluster"

    def __init__(self, runs: list[RunInfo]) -> None:
        self.runs = runs
        self.stopped: list[tuple[str, int]] = []
        self.cleaned: list[str] = []

    @override
    def prepare_images(self, request: ImageRequest) -> Images:
        raise NotImplementedError

    @override
    def copy_from_image(self, image: str, path: PurePosixPath, dest: Path, platform: str | None = None) -> None:
        raise NotImplementedError

    @override
    def start(self, spec: RunSpec) -> RunHandle:
        raise NotImplementedError

    @override
    def wait(self, handle: RunHandle, timeout: float | None = None) -> int:
        raise NotImplementedError

    @override
    def logs(self, handle: RunHandle, *, follow: bool = False) -> Iterator[str]:
        yield f"{handle.name} follow={follow}"
        yield "second line\n"

    @override
    def collect_results(self, handle: RunHandle, dest: Path) -> None:
        raise NotImplementedError

    @override
    def stop(self, handle: RunHandle, grace: int = 20) -> None:
        self.stopped.append((handle.run_id, grace))

    @override
    def cleanup(self, handle: RunHandle) -> None:
        self.cleaned.append(handle.run_id)
        self.runs = [run for run in self.runs if run.run_id != handle.run_id]

    @override
    def list_runs(self, labels: Mapping[str, str] | None = None) -> list[RunInfo]:
        return [run for run in self.runs if all(run.labels.get(k) == v for k, v in (labels or {}).items())]

    @override
    def endpoint(self, handle: RunHandle, port: int) -> str:
        if not handle.name.startswith("job-running"):
            raise BackendError(f"The run {handle.run_id} is not running")
        return f"http://{handle.name}.svc:{port}"


def info(run_id: str, state: str = "running", **labels: str) -> RunInfo:
    all_labels = {WEBUI_LABEL: "true", RUN_ID_LABEL: run_id, TASK_LABEL: "demo-1", "ssebench.agent": "dummy", **labels}
    name = f"job-{state}-{run_id}"
    return RunInfo(
        run_id=run_id,
        name=name,
        state=state,  # pyright: ignore[reportArgumentType]
        exit_code=None if state == "running" else 0,
        image="img",
        labels=all_labels,
        handle=RunHandle(run_id=run_id, name=name),
        created_at=f"2026-01-01T00:00:0{len(run_id)}Z",
    )


@pytest.fixture
def cluster(monkeypatch: pytest.MonkeyPatch) -> ClusterBackend:
    backend = ClusterBackend([info("a"), info("bb", "exited", **{RESULTS_LABEL: "/results/demo-1/m/dummy/bb"})])
    monkeypatch.setattr(runs, "resolve_backend", lambda name=None: backend)
    return backend


def run_cli(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    with pytest.raises(SystemExit) as exit_:
        main(["runs", *argv])
    captured = capsys.readouterr()
    return int(exit_.value.code or 0), captured.out, captured.err


def test_list_reports_the_backend_and_every_run_as_json(
    cluster: ClusterBackend, capsys: pytest.CaptureFixture[str]
) -> None:
    status, out, _ = run_cli(capsys, "list", "--json")

    document = json.loads(out)
    assert status == 0
    assert (document["backend"], document["supports_exec"]) == ("cluster", False)
    # Newest first
    assert [run["run_id"] for run in document["runs"]] == ["bb", "a"]
    finished = document["runs"][0]
    assert (finished["state"], finished["exit_code"], finished["task"], finished["agent"]) == (
        "exited",
        0,
        "demo-1",
        "dummy",
    )
    assert finished["results_dir"] == "/results/demo-1/m/dummy/bb"
    assert finished["reference_run"] is False


def test_list_skips_runs_that_have_no_id(cluster: ClusterBackend, capsys: pytest.CaptureFixture[str]) -> None:
    cluster.runs.append(info("", "exited"))

    _, out, _ = run_cli(capsys, "list", "--json")

    assert [run["run_id"] for run in json.loads(out)["runs"]] == ["bb", "a"]


def test_list_reports_only_ssebench_labels(cluster: ClusterBackend, capsys: pytest.CaptureFixture[str]) -> None:
    cluster.runs[0] = info("a", **{"org.example.unrelated": "x"})

    _, out, _ = run_cli(capsys, "list", "--json")

    labels = next(run for run in json.loads(out)["runs"] if run["run_id"] == "a")["labels"]
    assert "org.example.unrelated" not in labels and labels[RUN_ID_LABEL] == "a"


def test_list_prints_a_table_without_json(cluster: ClusterBackend, capsys: pytest.CaptureFixture[str]) -> None:
    status, out, _ = run_cli(capsys, "list")

    assert status == 0
    assert out.splitlines()[0].split() == ["RUN", "ID", "STATE", "TASK", "MODEL", "AGENT"]
    assert "bb" in out and "exited" in out


def test_inspect_finds_a_run_by_its_id(cluster: ClusterBackend, capsys: pytest.CaptureFixture[str]) -> None:
    status, out, _ = run_cli(capsys, "inspect", "a", "--json")

    assert status == 0
    assert json.loads(out)["state"] == "running"


def test_inspect_of_an_unknown_run_exits_with_the_not_found_status(
    cluster: ClusterBackend, capsys: pytest.CaptureFixture[str]
) -> None:
    status, out, err = run_cli(capsys, "inspect", "nope", "--json")

    assert (status, out) == (runs.EXIT_NOT_FOUND, "")
    assert "nope" in err


def test_a_reused_id_is_ambiguous_and_nothing_is_stopped(
    cluster: ClusterBackend, capsys: pytest.CaptureFixture[str]
) -> None:
    cluster.runs.append(info("a", **{TASK_LABEL: "demo-2"}))

    status, _, err = run_cli(capsys, "stop", "a")

    assert status == runs.EXIT_AMBIGUOUS and "2 runs" in err
    assert cluster.stopped == []


@pytest.mark.parametrize("bad", ["--help-me", ".hidden", "a b", "a;b", "latest", "x" * 65, "../etc"])
def test_a_run_id_that_cannot_be_one_is_refused_before_the_backend_is_asked(
    bad: str, cluster: ClusterBackend, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exit_:
        main(["runs", "stop", "--", bad])

    assert exit_.value.code == 2
    assert cluster.stopped == []


def test_stop_passes_the_grace_period(cluster: ClusterBackend, capsys: pytest.CaptureFixture[str]) -> None:
    status, _, _ = run_cli(capsys, "stop", "a", "--grace", "7")

    assert status == 0
    assert cluster.stopped == [("a", 7)]


def test_remove_cleans_up_and_checks_that_the_run_is_gone(
    cluster: ClusterBackend, capsys: pytest.CaptureFixture[str]
) -> None:
    status, _, _ = run_cli(capsys, "remove", "bb")

    assert status == 0
    assert cluster.cleaned == ["bb"]
    assert [run.run_id for run in cluster.runs] == ["a"]


def test_remove_fails_when_the_backend_left_the_run(
    cluster: ClusterBackend, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cluster, "cleanup", lambda handle: None)

    status, _, err = run_cli(capsys, "remove", "a")

    assert status == 1 and "still there" in err


def test_logs_are_printed_line_by_line(cluster: ClusterBackend, capsys: pytest.CaptureFixture[str]) -> None:
    status, out, _ = run_cli(capsys, "logs", "a", "--follow")

    assert status == 0
    assert out == "job-running-a follow=True\nsecond line\n"


def test_endpoint_prints_the_url_the_backend_gives(cluster: ClusterBackend, capsys: pytest.CaptureFixture[str]) -> None:
    status, out, _ = run_cli(capsys, "endpoint", "a", "4263", "--json")

    assert status == 0
    assert json.loads(out) == {"url": "http://job-running-a.svc:4263"}


def test_endpoint_of_a_run_that_is_not_running_fails(
    cluster: ClusterBackend, capsys: pytest.CaptureFixture[str]
) -> None:
    status, out, err = run_cli(capsys, "endpoint", "bb", "4263")

    assert (status, out) == (1, "")
    assert "not running" in err


def test_exec_is_refused_by_a_backend_without_it(cluster: ClusterBackend, capsys: pytest.CaptureFixture[str]) -> None:
    status, _, err = run_cli(capsys, "exec", "a", "--", "true")

    assert status == 1 and "cannot run commands" in err


def test_exec_replaces_the_process_with_the_backends_command(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    entry = {
        "Id": "abc",
        "Name": "/c",
        "Config": {"Image": "img", "Labels": {RUN_ID_LABEL: "r1", WEBUI_LABEL: "true"}},
        "State": {"Status": "running"},
    }

    def fake(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        out = "abc\n" if cmd[:2] == ["docker", "ps"] else json.dumps([entry])
        return subprocess.CompletedProcess(cmd, 0, out, "")

    executed: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", fake)
    monkeypatch.setattr(runs, "resolve_backend", lambda name=None: DockerBackend())

    def execvp(file: str, argv: list[str]) -> None:
        executed.append(list(argv))
        raise SystemExit(0)

    monkeypatch.setattr(os, "execvp", execvp)

    status, _, _ = run_cli(
        capsys,
        "exec",
        "r1",
        "--user",
        "model",
        "--workdir",
        "/src",
        "--tty",
        "--env",
        "SECRET",
        "--",
        "sh",
        "-c",
        "$X; y",
    )

    assert status == 0
    # The command reaches docker as separate words, and the value of SECRET is not among them.
    assert executed == [
        [
            "docker", "exec", "--interactive", "--tty", "--user", "model", "--workdir", "/src", "--env", "SECRET",
            "abc", "sh", "-c", "$X; y",
        ]
    ]  # fmt: skip


def test_docker_reaches_a_running_container_by_its_address(monkeypatch: pytest.MonkeyPatch) -> None:
    inspected = {
        "State": {"Running": True},
        "NetworkSettings": {"Networks": {"a": {"IPAddress": ""}, "b": {"IPAddress": "172.30.0.5"}}},
    }
    commands: list[list[str]] = []

    def fake(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, json.dumps([inspected]), "")

    monkeypatch.setattr(subprocess, "run", fake)

    url = DockerBackend().endpoint(DockerRun(run_id="r1", container="abc"), 4263)

    assert url == "http://172.30.0.5:4263"
    assert commands == [["docker", "inspect", "--type", "container", "abc"]]


def test_docker_has_no_endpoint_for_a_container_that_is_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    stopped = {"State": {"Running": False}, "NetworkSettings": {"Networks": {}}}
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, json.dumps([stopped]), "")
    )

    with pytest.raises(BackendError, match="not running"):
        DockerBackend().endpoint(DockerRun(run_id="r1", container="abc"), 4263)


def test_a_backend_that_implements_nothing_more_cannot_be_reached(tmp_path: Path) -> None:
    backend = ClusterBackend([])
    handle = RunHandle(run_id="r1")

    with pytest.raises(BackendError, match="cannot run commands"):
        backend.exec_argv(handle, ["true"])
    assert backend.supports_exec is False


# ==================== finished runs ====================


def write_run(root: Path, *parts: str, summary: object | None = None) -> Path:
    directory = root.joinpath(*parts)
    (directory / "archive").mkdir(parents=True)
    if summary is None:
        summary = {
            "task": {"id": parts[0]},
            "config": {"agent": parts[-2], "model": "/".join(parts[1:-2]), "mode": "sandbox", "reference_run": False},
            "patch_result": {"status": "failed"},
            "run_id": parts[-1],
            "started_at": "2026-01-01T00:00:00Z",
        }
    (directory / "summary.json").write_text(json.dumps(summary))
    return directory


def test_results_lists_finished_runs_at_any_depth(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "results"
    first = write_run(root, "demo-1", "provider", "model", "dummy", "r1")
    write_run(root, "demo-1", "none", "reference", "r2", summary=None)
    (root / "demo-1" / "none" / "reference" / "latest").symlink_to("r2")

    status, out, _ = run_cli(capsys, "results", "--dir", str(root), "--json")

    found = {run["run_id"]: run for run in json.loads(out)["runs"]}
    assert status == 0 and set(found) == {"r1", "r2"}
    assert found["r1"]["model"] == "provider/model"
    assert found["r1"]["dir"] == str(first.resolve())
    assert found["r1"]["status"] == "failed"


def test_results_skips_unfinished_and_damaged_runs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "results"
    (root / "demo-1" / "m" / "dummy" / "running").mkdir(parents=True)
    (root / "demo-1" / "m" / "dummy" / "running" / "result.json").write_text("{}")
    damaged = write_run(root, "demo-1", "m", "dummy", "torn")
    (damaged / "summary.json").write_text("{not json")
    write_run(root, "demo-1", "m", "dummy", "notask", summary={"config": {}})
    write_run(root, "demo-1", "m", "dummy", "badid", summary={"task": {"id": "t"}, "run_id": "../x"})

    _, out, _ = run_cli(capsys, "results", "--dir", str(root), "--json")

    assert json.loads(out) == {"runs": []}


def test_results_of_a_missing_directory_is_empty(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    status, out, _ = run_cli(capsys, "results", "--dir", str(tmp_path / "none"), "--json")

    assert (status, json.loads(out)) == (0, {"runs": []})


def test_results_are_newest_first(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "results"
    for name, started in (("old", "2026-01-01T00:00:00Z"), ("new", "2026-02-01T00:00:00Z")):
        write_run(
            root,
            "demo-1",
            "m",
            "dummy",
            name,
            summary={"task": {"id": "demo-1"}, "config": {}, "run_id": name, "started_at": started},
        )

    _, out, _ = run_cli(capsys, "results", "--dir", str(root), "--json")

    assert [run["run_id"] for run in json.loads(out)["runs"]] == ["new", "old"]
