import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from ssebench.cli import main
from ssebench.dataset import publish, verify
from ssebench.dataset.generate import build_manifest, render_manifest
from ssebench.pipe import REGISTRY
from ssebench.runner.result import PatchResult
from ssebench.tasks.manifest import ImagesLock, LockedImage, files_digest, task_files

MakeTask = Callable[..., Path]

CHECKOUT = Path(__file__).resolve().parents[2]
PILOT = CHECKOUT / "datasets" / "pilot"
COMMIT = "0123456789abcdef0123456789abcdef01234567"
IMAGE = "sha256:" + "11" * 32
PUSHED = "sha256:" + "22" * 32
REMOTE = "registry.test/ssebench"


def run_cli(*argv: str) -> int:
    with pytest.raises(SystemExit) as exit_info:
        main(list(argv))
    code = exit_info.value.code
    assert isinstance(code, int)
    return code


class FakeDocker:
    """Answers `docker image inspect`, `tag` and `push`, and records them."""

    def __init__(self) -> None:
        self.image_id = IMAGE
        self.arch = "amd64"
        self.digests: dict[str, str] = {}
        self.commands: list[list[str]] = []

    def __call__(self, cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        assert cmd[0] == "docker"
        self.commands.append(cmd)
        done = subprocess.CompletedProcess[str]
        match cmd[1:3]:
            case ["image", "inspect"]:
                return done(cmd, 0, f"{self.image_id} {self.arch}\n", "")
            case ["push", ref]:
                digest = self.digests.get(ref, PUSHED)
                return done(cmd, 0, f"{ref.rpartition(':')[2]}: digest: {digest} size: 856\n", "")
        return done(cmd, 0, "", "")

    def pushed(self) -> list[str]:
        return [cmd[2] for cmd in self.commands if cmd[1] == "push"]


@pytest.fixture
def docker(monkeypatch: pytest.MonkeyPatch) -> FakeDocker:
    fake = FakeDocker()
    monkeypatch.setattr(publish.subprocess, "run", fake)
    return fake


@pytest.fixture
def dataset(tmp_path: Path, make_task: MakeTask) -> Path:
    path = tmp_path / "demo"
    for task in ("demo-1", "demo-2"):
        _ = make_task(path, task)
    _ = (path / "manifest.json").write_text(render_manifest(build_manifest(path)))
    return path


def grade() -> PatchResult:
    return PatchResult(build_success=True, pov_passed=1, pov_total=1, func_test_success=True, intent_test_success=True)


def record_verdict(output: Path, task: str, image: str | None = IMAGE, ok: bool = True) -> None:
    """Write the result of verifying a task: the reference passes everything, the dummy fails the PoCs' fix."""
    checks: list[verify.Check] = ["build", "poc", "function_test", "intent_test"]
    v = verify.TaskVerdict(task=task, base="base-generic-c:1.0.0", checks=checks, pocs=1)
    v.runs[verify.REFERENCE] = verify.judge(verify.REFERENCE, grade(), checks, 1)
    dummy = PatchResult(build_success=True, pov_passed=0, pov_total=1, func_test_success=ok, intent_test_success=False)
    v.runs[verify.DUMMY] = verify.judge(verify.DUMMY, dummy, checks, 1)
    for run in v.runs.values():
        run.image = image
    _ = verify.write_verdict(output, v)


@pytest.fixture
def target(dataset: Path, tmp_path: Path) -> publish.Target:
    return publish.Target(dataset=dataset, version="demo-v1", output=tmp_path / "out", registry=REMOTE, revision=COMMIT)


def task_report(dataset: Path, task: str) -> verify.TaskReport:
    [report] = verify.select_tasks(verify.load_tasks(dataset), [task])
    return report


# Publishing


def test_publishes_the_graded_image(docker: FakeDocker, dataset: Path, target: publish.Target) -> None:
    record_verdict(target.output, "demo-1")

    published = publish.publish_task(target, task_report(dataset, "demo-1"))

    local = f"{REGISTRY}/case/demo/demo-1"
    remote = f"{REMOTE}/case/demo/demo-1"
    # The tag that no later commit reuses goes first, so that the moving tag never leads the record.
    assert docker.pushed() == [f"{remote}:demo-v1-0123456", f"{remote}:demo-v1"]
    assert ["docker", "tag", local, f"{remote}:demo-v1"] in docker.commands
    assert published.digest == PUSHED
    assert published.tags == ["demo-v1-0123456", "demo-v1"]
    assert published.files_sha256 == files_digest(task_files(dataset / "demo-1"))
    assert published.revision == COMMIT
    [record] = publish.read_records(target.output / publish.RECORDS)
    assert record == published


def test_a_task_without_a_result_is_not_published(docker: FakeDocker, dataset: Path, target: publish.Target) -> None:
    with pytest.raises(publish.PublishError, match="no verification result"):
        _ = publish.publish_task(target, task_report(dataset, "demo-1"))
    assert docker.commands == []


def test_a_task_that_failed_is_not_published(docker: FakeDocker, dataset: Path, target: publish.Target) -> None:
    record_verdict(target.output, "demo-1", ok=False)

    with pytest.raises(publish.PublishError, match="did not verify"):
        _ = publish.publish_task(target, task_report(dataset, "demo-1"))
    assert docker.pushed() == []


def test_a_verification_that_did_not_record_the_image(
    docker: FakeDocker, dataset: Path, target: publish.Target
) -> None:
    record_verdict(target.output, "demo-1", image=None)

    with pytest.raises(publish.PublishError, match="did not record the case image"):
        _ = publish.publish_task(target, task_report(dataset, "demo-1"))
    assert docker.pushed() == []


def test_an_image_that_was_rebuilt_since_is_not_published(
    docker: FakeDocker, dataset: Path, target: publish.Target
) -> None:
    record_verdict(target.output, "demo-1")
    docker.image_id = "sha256:" + "33" * 32

    with pytest.raises(publish.PublishError, match="not the image that was graded"):
        _ = publish.publish_task(target, task_report(dataset, "demo-1"))
    assert docker.pushed() == []


def test_only_amd64_images_are_published(docker: FakeDocker, dataset: Path, target: publish.Target) -> None:
    record_verdict(target.output, "demo-1")
    docker.arch = "arm64"

    with pytest.raises(publish.PublishError, match="arm64"):
        _ = publish.publish_task(target, task_report(dataset, "demo-1"))
    assert docker.pushed() == []


def test_tags_that_reach_different_images_are_an_error(
    docker: FakeDocker, dataset: Path, target: publish.Target
) -> None:
    record_verdict(target.output, "demo-1")
    docker.digests[f"{REMOTE}/case/demo/demo-1:demo-v1"] = "sha256:" + "44" * 32

    with pytest.raises(publish.PublishError, match="different images"):
        _ = publish.publish_task(target, task_report(dataset, "demo-1"))
    assert not (target.output / publish.RECORDS).exists()


def test_a_push_that_reports_no_digest_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(publish.subprocess, "run", lambda cmd, **_: subprocess.CompletedProcess(cmd, 0, "done\n", ""))

    with pytest.raises(publish.PublishError, match="did not report a digest"):
        _ = publish.push("registry.test/x:y")


def test_a_failed_push_is_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        publish.subprocess, "run", lambda cmd, **_: subprocess.CompletedProcess(cmd, 1, "", "denied: not allowed")
    )

    with pytest.raises(publish.PublishError, match="denied: not allowed"):
        _ = publish.push("registry.test/x:y")


def test_cli_publishes_the_tasks_with_results(
    docker: FakeDocker, dataset: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "out"
    record_verdict(output, "demo-2")
    args = ("dataset", "publish", "--dir", str(dataset), "--output", str(output), "--registry", REMOTE + "/")

    assert run_cli(*args, "--revision", COMMIT) == 0

    assert capsys.readouterr().out.strip().endswith(f"case/demo/demo-2@{PUSHED} as demo-v1-0123456, demo-v1")
    assert docker.pushed() == [f"{REMOTE}/case/demo/demo-2:demo-v1-0123456", f"{REMOTE}/case/demo/demo-2:demo-v1"]
    assert [r.task for r in publish.read_records(output / publish.RECORDS)] == ["demo-2"]


def test_cli_exits_1_when_a_task_cannot_be_published(
    docker: FakeDocker, dataset: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "out"
    record_verdict(output, "demo-1")
    args = ("dataset", "publish", "--dir", str(dataset), "--output", str(output), "--registry", REMOTE)

    assert run_cli(*args, "--revision", COMMIT, "demo-1", "demo-2") == 1

    assert "demo-2: there is no verification result" in capsys.readouterr().err
    assert len(docker.pushed()) == 2  # demo-1 still went out


def test_cli_needs_a_full_commit(docker: FakeDocker, dataset: Path, tmp_path: Path) -> None:
    args = ("dataset", "publish", "--dir", str(dataset), "--output", str(tmp_path), "--registry", REMOTE)

    assert run_cli(*args, "--revision", "abc123") == 1
    assert docker.commands == []


# The images lock


def publication(dataset: Path, task: str, digest: str = PUSHED, revision: str = COMMIT) -> publish.Publication:
    return publish.Publication(
        task=task,
        dataset="demo",
        version="demo-v1",
        image=f"case/demo/{task}",
        tags=["demo-v1"],
        digest=digest,
        files_sha256=files_digest(task_files(dataset / task)),
        revision=revision,
    )


def test_lock_from_records(dataset: Path) -> None:
    lock = publish.build_lock(dataset, [publication(dataset, "demo-2"), publication(dataset, "demo-1")], None)

    assert (lock.dataset, lock.version) == ("demo", "demo-v1")
    assert list(lock.images) == ["demo-1", "demo-2"]
    assert lock.images["demo-1"].digest == PUSHED
    assert publish.render_lock(lock) == publish.render_lock(publish.build_lock(dataset, [], lock))


def test_records_replace_the_images_of_the_previous_lock(dataset: Path) -> None:
    previous = publish.build_lock(dataset, [publication(dataset, "demo-1"), publication(dataset, "demo-2")], None)
    newer = "sha256:" + "55" * 32

    lock = publish.build_lock(dataset, [publication(dataset, "demo-2", digest=newer)], previous)

    assert lock.images["demo-1"].digest == PUSHED
    assert lock.images["demo-2"].digest == newer


def test_images_of_changed_tasks_are_dropped(dataset: Path) -> None:
    previous = publish.build_lock(dataset, [publication(dataset, "demo-1"), publication(dataset, "demo-2")], None)
    _ = (dataset / "demo-2" / "sse" / "run.sh").write_text('#!/bin/sh\n./demo --fixed "$1"\n')

    lock = publish.build_lock(dataset, [], previous)

    assert list(lock.images) == ["demo-1"]


def test_a_lock_of_another_version_is_not_carried_over(dataset: Path) -> None:
    previous = ImagesLock(dataset="demo", version="demo-v0", images={"demo-1": image(dataset, "demo-1")})

    assert publish.build_lock(dataset, [], previous).images == {}


def image(dataset: Path, task: str) -> LockedImage:
    return LockedImage(digest=PUSHED, files_sha256=files_digest(task_files(dataset / task)), revision=COMMIT)


def test_a_record_for_other_task_files_is_an_error(dataset: Path) -> None:
    record = publication(dataset, "demo-1")
    _ = (dataset / "demo-1" / "sse" / "run.sh").write_text('#!/bin/sh\n./demo --fixed "$1"\n')

    with pytest.raises(publish.LockError, match="other task files"):
        _ = publish.build_lock(dataset, [record], None)


def test_a_record_for_another_dataset_version_is_an_error(dataset: Path) -> None:
    record = publication(dataset, "demo-1").model_copy(update={"version": "demo-v0"})

    with pytest.raises(publish.LockError, match="demo-v0"):
        _ = publish.build_lock(dataset, [record], None)


def test_an_invalid_record_is_an_error(tmp_path: Path) -> None:
    _ = (tmp_path / "demo-1.json").write_text('{"task": "demo-1"}')

    with pytest.raises(publish.LockError, match="not a valid publication record"):
        _ = publish.read_records(tmp_path)


def test_cli_writes_the_lock(dataset: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    records = tmp_path / "records"
    records.mkdir()
    for task in ("demo-1", "demo-2"):
        _ = (records / f"{task}.json").write_text(publication(dataset, task).model_dump_json())
    out = tmp_path / "images.lock.json"

    assert run_cli("dataset", "lock", str(dataset), "--records", str(records), "-o", str(out)) == 0

    assert not (dataset / "images.lock.json").exists()
    assert json.loads(out.read_text())["images"]["demo-2"] == {
        "digest": PUSHED,
        "files_sha256": files_digest(task_files(dataset / "demo-2")),
        "revision": COMMIT,
    }
    assert "wrote" in capsys.readouterr().out

    # Without records, the lock in the dataset keeps its still-valid images.
    _ = (dataset / "images.lock.json").write_text(out.read_text())
    assert run_cli("dataset", "lock", str(dataset)) == 0
    assert (dataset / "images.lock.json").read_text() == out.read_text()


def test_cli_checks_the_lock(dataset: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cli("dataset", "lock", str(dataset), "--check") == 1
    assert "is missing" in capsys.readouterr().err

    lock = publish.build_lock(dataset, [publication(dataset, "demo-1")], None)
    _ = (dataset / "images.lock.json").write_text(publish.render_lock(lock))
    assert run_cli("dataset", "lock", str(dataset), "--check") == 0

    # A lock that lags behind a changed task is not an error; `lock` drops that image.
    _ = (dataset / "demo-1" / "sse" / "run.sh").write_text('#!/bin/sh\n./demo --fixed "$1"\n')
    assert run_cli("dataset", "lock", str(dataset), "--check") == 0

    other = lock.model_copy(update={"version": "demo-v0"})
    _ = (dataset / "images.lock.json").write_text(publish.render_lock(other))
    assert run_cli("dataset", "lock", str(dataset), "--check") == 1
    assert "demo-v0" in capsys.readouterr().err

    unknown = lock.model_copy(update={"images": {"gone": image(dataset, "demo-2")}})
    _ = (dataset / "images.lock.json").write_text(publish.render_lock(unknown))
    assert run_cli("dataset", "lock", str(dataset), "--check") == 1
    assert "gone, which is not a task" in capsys.readouterr().err

    _ = (dataset / "images.lock.json").write_text("{}")
    assert run_cli("dataset", "lock", str(dataset), "--check") == 1
    assert "not a valid images lock" in capsys.readouterr().err


# The committed lock


def test_the_committed_lock_is_valid() -> None:
    schema = json.loads((CHECKOUT / "datasets" / "schema" / "images-lock.schema.json").read_text())
    lock = json.loads((PILOT / "images.lock.json").read_text())

    assert list(Draft202012Validator(schema).iter_errors(lock)) == []
    assert publish.lock_problems(PILOT) == []
    assert run_cli("dataset", "lock", str(PILOT), "--check") == 0
