import json
import subprocess
import threading
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from ssebench import paths, settings
from ssebench.cli import main
from ssebench.cli.cli import build_parser
from ssebench.dataset.generate import build_manifest, render_manifest
from ssebench.dataset.publish import render_lock
from ssebench.pipe import REGISTRY
from ssebench.tasks import catalog
from ssebench.tasks.catalog import (
    CATALOG_ENV,
    IMAGES_LOCK_ENV,
    CatalogError,
    CatalogTask,
    catalog_location,
    load_catalog,
    manifest_location,
)
from ssebench.tasks.manifest import ImagesLock, LockedImage, files_digest

# This checkout: bench/tests/ is two levels below the repository root.
CHECKOUT = Path(__file__).resolve().parents[2]
BUNDLED = CHECKOUT / "datasets" / "pilot" / "manifest.json"
TASK = "gjson-196-bf4efcb"

Serve = Callable[[dict[str, bytes]], str]


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CATALOG_ENV, raising=False)
    monkeypatch.delenv(IMAGES_LOCK_ENV, raising=False)
    monkeypatch.setenv(paths.HOME_ENV, str(CHECKOUT))
    monkeypatch.setattr(settings, "dotenv", dict)


@pytest.fixture
def serve() -> Iterator[Serve]:
    """Start HTTP servers on loopback that answer GET for the given paths and 404 otherwise."""
    servers: list[ThreadingHTTPServer] = []

    def start(routes: dict[str, bytes]) -> str:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                body = routes.get(self.path)
                if body is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                _ = self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        servers.append(server)
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        return f"http://127.0.0.1:{server.server_address[1]}"

    yield start
    for server in servers:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("https://example.org/pilot/manifest.json", "https://example.org/pilot/manifest.json"),
        ("https://example.org/pilot/v1.json?sig=abc", "https://example.org/pilot/v1.json?sig=abc"),
        ("http://catalog:8080", "http://catalog:8080/manifest.json"),
        ("http://catalog:8080/", "http://catalog:8080/manifest.json"),
        ("https://example.org/catalog/?key=1", "https://example.org/catalog/manifest.json?key=1"),
    ],
)
def test_manifest_location_of_a_url(location: str, expected: str) -> None:
    assert manifest_location(location) == expected


def test_manifest_location_of_a_path(tmp_path: Path) -> None:
    assert manifest_location(str(tmp_path)) == str(tmp_path / "manifest.json")
    assert manifest_location(str(tmp_path / "other.json")) == str(tmp_path / "other.json")


def test_catalog_location_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    assert catalog_location() == str(BUNDLED)
    monkeypatch.setattr(settings, "dotenv", lambda: {CATALOG_ENV: "http://from-dotenv"})
    assert catalog_location() == "http://from-dotenv"
    monkeypatch.setenv(CATALOG_ENV, "http://from-env")
    assert catalog_location() == "http://from-env"
    assert catalog_location(" http://from-flag ") == "http://from-flag"


def test_default_is_the_bundled_manifest() -> None:
    c = load_catalog()

    assert c.location == str(BUNDLED)
    assert c.manifest.dataset == "pilot"
    assert c.task(TASK).metadata.source == "/src/gjson"


def test_path_to_a_manifest_file() -> None:
    c = load_catalog(str(BUNDLED))

    assert c.location == str(BUNDLED)
    assert TASK in [t.id for t in c.manifest.tasks]


def test_path_to_a_dataset_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CATALOG_ENV, str(BUNDLED.parent))

    assert load_catalog().location == str(BUNDLED)


def test_manifest_url(serve: Serve) -> None:
    base = serve({"/datasets/pilot-v1.json": BUNDLED.read_bytes()})

    c = load_catalog(f"{base}/datasets/pilot-v1.json")

    assert c.task(TASK).image == f"case/pilot/{TASK}"


def test_catalog_service_url(serve: Serve, monkeypatch: pytest.MonkeyPatch) -> None:
    # A catalog service serves its manifest at /manifest.json, next to /tasks.
    base = serve({"/manifest.json": BUNDLED.read_bytes(), "/tasks": b"[]"})
    monkeypatch.setenv(CATALOG_ENV, base + "/")

    c = load_catalog()

    assert c.location == f"{base}/manifest.json"
    assert c.task(TASK).metadata.id == TASK


def test_unknown_task() -> None:
    with pytest.raises(LookupError, match="not in the catalog"):
        _ = CatalogTask(load_catalog(), "missing")


@pytest.mark.parametrize(("routes", "error"), [({}, "Cannot read"), ({"/manifest.json": b"{}"}, "not a valid")])
def test_unreadable_catalog(serve: Serve, routes: dict[str, bytes], error: str) -> None:
    with pytest.raises(CatalogError, match=error):
        _ = load_catalog(serve(routes))


def test_missing_manifest_file(tmp_path: Path) -> None:
    with pytest.raises(CatalogError, match="Cannot read"):
        _ = load_catalog(str(tmp_path))


def test_catalog_task(serve: Serve) -> None:
    task = CatalogTask(load_catalog(serve({"/manifest.json": BUNDLED.read_bytes()})), TASK)

    assert task.docker_image_name == f"{REGISTRY}/case/pilot/{TASK}:pilot-v1"
    assert task.get_task_metadata().id == TASK


class Docker:
    """Stands in for `docker pull`, `docker tag` and the local case image build."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, pull_ok: bool):
        self.pulled: list[str] = []
        self.tagged: list[tuple[str, str]] = []
        self.built: list[tuple[Path, str]] = []
        self.pull_ok: bool = pull_ok
        monkeypatch.setattr(catalog.subprocess, "run", self.run)
        monkeypatch.setattr(catalog, "docker_build_case", lambda folder, image: self.built.append((folder, image)))

    def run(self, cmd: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
        if cmd[:2] == ["docker", "tag"]:
            self.tagged.append((cmd[2], cmd[3]))
            return subprocess.CompletedProcess(cmd, 0)
        assert cmd[:2] == ["docker", "pull"]
        self.pulled.append(cmd[2])
        return subprocess.CompletedProcess(cmd, 0 if self.pull_ok else 1)


def test_pulls_the_case_image(monkeypatch: pytest.MonkeyPatch) -> None:
    docker = Docker(monkeypatch, pull_ok=True)
    task = CatalogTask(load_catalog(), TASK)

    assert task.docker_image(None) == f"{REGISTRY}/case/pilot/{TASK}:pilot-v1"
    assert docker.pulled == [task.docker_image_name]
    assert docker.tagged == []
    assert docker.built == []


def test_builds_from_the_bundled_dataset_when_the_pull_fails(serve: Serve, monkeypatch: pytest.MonkeyPatch) -> None:
    docker = Docker(monkeypatch, pull_ok=False)
    task = CatalogTask(load_catalog(serve({"/manifest.json": BUNDLED.read_bytes()})), TASK)

    assert task.docker_image(None) == task.docker_image_name
    assert docker.built == [(CHECKOUT / "datasets" / "pilot" / TASK, task.docker_image_name)]


def test_builds_from_the_folder_next_to_the_manifest(
    tmp_path: Path, make_task: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path))  # a home without this dataset
    folder = make_task(tmp_path / "demo", "demo-task")
    _ = (tmp_path / "demo" / "manifest.json").write_text(render_manifest(build_manifest(tmp_path / "demo")))
    docker = Docker(monkeypatch, pull_ok=False)

    task = CatalogTask(load_catalog(str(tmp_path / "demo")), "demo-task")
    _ = task.docker_image(None)
    assert docker.built == [(folder, f"{REGISTRY}/case/demo/demo-task:demo-v1")]

    # A folder that no longer matches the manifest would build a different task.
    _ = (folder / "sse" / "build.sh").write_text("#!/bin/sh\nmake all\n")
    with pytest.raises(CatalogError, match="no local copy"):
        _ = task.docker_image(None)


def test_fails_without_a_local_copy(serve: Serve, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path))
    _ = Docker(monkeypatch, pull_ok=False)
    task = CatalogTask(load_catalog(serve({"/manifest.json": BUNDLED.read_bytes()})), TASK)

    with pytest.raises(CatalogError, match="no local copy"):
        _ = task.docker_image(None)


DIGEST = "sha256:" + "ab" * 32
COMMIT = "c" * 40


def locked_dataset(
    root: Path, make_task: Callable[..., Path], pinned: bool = True, stale: bool = False
) -> tuple[Path, Path]:
    """A dataset of one task, with a manifest and an images lock that pins the task, and the task folder."""
    dataset = root / "demo"
    folder = make_task(dataset, "demo-task")
    manifest = build_manifest(dataset)
    _ = (dataset / "manifest.json").write_text(render_manifest(manifest))
    [entry] = manifest.tasks
    assert entry.files is not None
    files = files_digest(entry.files)[::-1] if stale else files_digest(entry.files)
    images = {"demo-task": LockedImage(digest=DIGEST, files_sha256=files, revision=COMMIT)} if pinned else {}
    lock = ImagesLock(dataset="demo", version=manifest.version, images=images)
    _ = (dataset / "images.lock.json").write_text(render_lock(lock))
    return dataset, folder


def test_pulls_the_digest_that_the_lock_pins(
    tmp_path: Path, make_task: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset, _ = locked_dataset(tmp_path, make_task)
    docker = Docker(monkeypatch, pull_ok=True)

    task = CatalogTask(load_catalog(str(dataset)), "demo-task")

    assert task.docker_image(None) == f"{REGISTRY}/case/demo/demo-task:demo-v1"
    assert docker.pulled == [f"{REGISTRY}/case/demo/demo-task@{DIGEST}"]
    # The image is tagged as the runs name it, so that they use exactly the pinned image.
    assert docker.tagged == [(f"{REGISTRY}/case/demo/demo-task@{DIGEST}", task.docker_image_name)]
    assert docker.built == []


def test_a_pinned_image_that_cannot_be_pulled_is_built(
    tmp_path: Path, make_task: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset, folder = locked_dataset(tmp_path, make_task)
    docker = Docker(monkeypatch, pull_ok=False)

    task = CatalogTask(load_catalog(str(dataset)), "demo-task")
    _ = task.docker_image(None)

    assert docker.pulled == [f"{REGISTRY}/case/demo/demo-task@{DIGEST}"]
    assert docker.built == [(folder, task.docker_image_name)]


def test_a_lock_for_other_task_files_is_ignored(
    tmp_path: Path, make_task: Callable[..., Path], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    dataset, _ = locked_dataset(tmp_path, make_task, stale=True)
    docker = Docker(monkeypatch, pull_ok=True)

    task = CatalogTask(load_catalog(str(dataset)), "demo-task")
    _ = task.docker_image(None)

    assert docker.pulled == [task.docker_image_name]
    assert "built from other files" in caplog.text


def test_a_task_the_lock_does_not_list_is_pulled_by_tag(
    tmp_path: Path, make_task: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset, _ = locked_dataset(tmp_path, make_task, pinned=False)
    docker = Docker(monkeypatch, pull_ok=True)

    task = CatalogTask(load_catalog(str(dataset)), "demo-task")
    _ = task.docker_image(None)

    assert docker.pulled == [task.docker_image_name]


def test_a_lock_for_another_dataset_version_is_ignored(
    tmp_path: Path, make_task: Callable[..., Path], caplog: pytest.LogCaptureFixture
) -> None:
    dataset, _ = locked_dataset(tmp_path, make_task)
    lock = ImagesLock(dataset="demo", version="demo-v0", images={})
    _ = (dataset / "images.lock.json").write_text(render_lock(lock))

    task = CatalogTask(load_catalog(str(dataset)), "demo-task")

    assert task.digest is None
    assert "demo-v0" in caplog.text


def test_the_lock_setting_names_another_lock(
    tmp_path: Path, make_task: Callable[..., Path], serve: Serve, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset, _ = locked_dataset(tmp_path, make_task, pinned=False)
    pinned, _ = locked_dataset(tmp_path / "other", make_task)
    lock = (pinned / "images.lock.json").read_bytes()

    monkeypatch.setenv(IMAGES_LOCK_ENV, str(pinned / "images.lock.json"))
    assert CatalogTask(load_catalog(str(dataset)), "demo-task").digest == DIGEST

    monkeypatch.setenv(IMAGES_LOCK_ENV, serve({"/images.lock.json": lock}) + "/images.lock.json")
    assert CatalogTask(load_catalog(str(dataset)), "demo-task").digest == DIGEST


def test_a_catalog_service_has_no_lock_of_its_own(serve: Serve) -> None:
    task = CatalogTask(load_catalog(serve({"/manifest.json": BUNDLED.read_bytes()})), TASK)

    assert task.digest is None


@pytest.mark.parametrize("text", ["not json", '{"dataset": "demo"}'])
def test_an_invalid_lock_is_an_error(tmp_path: Path, make_task: Callable[..., Path], text: str) -> None:
    dataset, _ = locked_dataset(tmp_path, make_task)
    _ = (dataset / "images.lock.json").write_text(text)

    with pytest.raises(CatalogError, match="not a valid images lock"):
        _ = CatalogTask(load_catalog(str(dataset)), "demo-task")


def test_a_missing_lock_named_by_the_setting_is_an_error(
    tmp_path: Path, make_task: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset, _ = locked_dataset(tmp_path, make_task)
    monkeypatch.setenv(IMAGES_LOCK_ENV, str(tmp_path / "missing.json"))

    with pytest.raises(CatalogError, match="Cannot read the images lock"):
        _ = CatalogTask(load_catalog(str(dataset)), "demo-task")


def test_build_skips_the_pull(tmp_path: Path, make_task: Callable[..., Path], monkeypatch: pytest.MonkeyPatch) -> None:
    dataset, folder = locked_dataset(tmp_path, make_task)
    docker = Docker(monkeypatch, pull_ok=True)

    task = CatalogTask(load_catalog(str(dataset)), "demo-task", build_locally=True)

    assert task.docker_image(None) == f"{REGISTRY}/case/demo/demo-task:demo-v1"
    assert docker.pulled == []
    assert docker.built == [(folder, task.docker_image_name)]


def test_build_needs_the_task_folder(serve: Serve, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path))
    docker = Docker(monkeypatch, pull_ok=True)

    with pytest.raises(CatalogError, match="no local copy"):
        _ = CatalogTask(load_catalog(serve({"/manifest.json": BUNDLED.read_bytes()})), TASK, build_locally=True)
    assert docker.pulled == docker.built == []


def test_run_takes_build() -> None:
    parser, _ = build_parser()
    run = ["run", "--agent", "dummy", "--task", TASK]

    assert parser.parse_args(run).build is False
    assert parser.parse_args([*run, "--build"]).build is True


def run_cli(*argv: str) -> int:
    with pytest.raises(SystemExit) as exit:
        main(list(argv))
    code = exit.value.code
    assert isinstance(code, int)
    return code


def test_tasks_list(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cli("tasks", "list") == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["ID", "LANGUAGE", "PROJECT"]
    assert [TASK, "go", "gjson"] in [line.split() for line in lines]


def test_tasks_list_json(serve: Serve, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cli("tasks", "list", "--json", "--catalog", serve({"/manifest.json": BUNDLED.read_bytes()})) == 0

    tasks = {t["id"]: t for t in json.loads(capsys.readouterr().out)}
    assert tasks[TASK]["image"] == f"{REGISTRY}/case/pilot/{TASK}"
    assert "metadata" not in tasks[TASK] and "files" not in tasks[TASK]


def test_tasks_list_local(tmp_path: Path, make_task: Callable[..., Path], capsys: pytest.CaptureFixture[str]) -> None:
    _ = make_task(tmp_path / "demo", "demo-task")

    assert run_cli("tasks", "list", "--json", "--local", str(tmp_path / "demo")) == 0
    assert [t["id"] for t in json.loads(capsys.readouterr().out)] == ["demo-task"]


def test_tasks_list_unreadable_catalog(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_cli("tasks", "list", "--catalog", str(tmp_path / "missing.json")) == 1
    assert "Cannot read the catalog" in capsys.readouterr().err
