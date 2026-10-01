"""The artifact plugin indexes the run's results directory, not just the archive."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType

import pytest

MAIN = Path(__file__).resolve().parents[1] / "main.py"


@pytest.fixture
def main() -> ModuleType:
    spec = importlib.util.spec_from_file_location("artifact_main", MAIN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def populate(results: Path, archive: Path) -> None:
    for name in ("result.json", "final.patch", "commits.log", "source.tar.gz", "daemon.log", "scriptrunner-1.log"):
        write(results / name)
    write(archive / "dialog.jsonl")
    write(archive / "plugins" / "artifact.log")
    write(archive / "plugins" / "results.json")
    write(archive / "artifact" / "stale.json")


def run(main: ModuleType, monkeypatch: pytest.MonkeyPatch, results: Path, archive: Path) -> dict:
    monkeypatch.setenv("SSE_RESULTS", str(results))
    monkeypatch.setenv("SSE_ARCHIVE", str(archive))
    assert main.main() == 0
    return json.loads((archive / "artifact" / "manifest.json").read_text())


EXPECTED = {
    "archive/dialog.jsonl": "agent",
    "commits.log": "daemon",
    "daemon.log": "entrypoint",
    "final.patch": "daemon",
    "result.json": "evaluator",
    "scriptrunner-1.log": "daemon",
    "source.tar.gz": "evaluator",
}


def test_archive_inside_results(main: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    results = tmp_path / "results"
    archive = results / "archive"
    populate(results, archive)

    manifest = run(main, monkeypatch, results, archive)

    assert {f["path"]: f["producer"] for f in manifest["files"]} == EXPECTED
    assert manifest["file_count"] == len(EXPECTED)


def test_archive_mounted_at_a_second_path(main: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # The sandbox mounts the archive at SSE_ARCHIVE and, through the run
    # directory, inside SSE_RESULTS; a symlink stands in for the second mount.
    results = tmp_path / "results"
    archive = results / "archive"
    populate(results, archive)
    mount = tmp_path / "sse-archive"
    os.symlink(archive, mount)

    manifest = run(main, monkeypatch, results, mount)

    assert {f["path"] for f in manifest["files"]} == set(EXPECTED)


def test_archive_outside_results(main: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    results = tmp_path / "results"
    archive = tmp_path / "archive-volume"
    populate(results, archive)

    manifest = run(main, monkeypatch, results, archive)

    assert {f["path"] for f in manifest["files"]} == set(EXPECTED)


def test_checksums(main: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    results = tmp_path / "results"
    write(results / "final.patch", "diff\n")

    manifest = run(main, monkeypatch, results, results / "archive")

    [entry] = manifest["files"]
    assert entry["size_bytes"] == 5
    assert entry["sha256"] == hashlib.sha256(b"diff\n").hexdigest()


def test_missing_results_directory_skips(main: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    skip = tmp_path / "skip"
    monkeypatch.setenv("SSE_PLUGIN_SKIP_FILE", str(skip))
    monkeypatch.setenv("SSE_RESULTS", str(tmp_path / "missing"))
    monkeypatch.setenv("SSE_ARCHIVE", str(tmp_path / "archive"))

    assert main.main() == 0

    assert "is not a directory" in skip.read_text()
    assert not (tmp_path / "archive" / "artifact").exists()
