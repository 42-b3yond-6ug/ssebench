"""The wheel carries the assets that the CLI needs without a checkout, and its metadata is complete.

The tests build with hatchling as `uv build` does: the sdist from the repository, then the wheel from
the unpacked sdist.
"""

import importlib.util
import shutil
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

CHECKOUT = Path(__file__).resolve().parents[2]
BENCH = CHECKOUT / "bench"
DATA = "ssebench/_data/"


def load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("hatch_build", BENCH / "hatch_build.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hatch_build = load_hook()


def build(project: Path, target: str, out: Path) -> Path:
    result = subprocess.run(
        [sys.executable, "-m", "hatchling", "build", "-t", target, "-d", str(out)],
        cwd=project,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    [artifact] = out.iterdir()
    return artifact


def extract_sdist(sdist: Path, into: Path) -> Path:
    with tarfile.open(sdist) as tar:
        tar.extractall(into, filter="data")
    [root] = into.iterdir()
    return root


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("build")
    sdist = build(BENCH, "sdist", tmp / "sdist")
    return build(extract_sdist(sdist, tmp / "unpacked"), "wheel", tmp / "wheel")


def wheel_names(wheel: Path) -> set[str]:
    with zipfile.ZipFile(wheel) as z:
        return set(z.namelist())


def test_the_hook_lists_what_the_cli_needs() -> None:
    files = set(hatch_build.data_files(CHECKOUT).values())

    assert {
        "pyproject.toml",
        "uv.lock",
        ".env.example",
        "agents/dummy/agent.yaml",
        "agents/reference/Dockerfile",
        "models/anthropic-claude.yaml",
        "deploy/compose/docker-compose.yaml",
        "images/litellm/Dockerfile",
        "images/litellm/config_gen.py",
        "images/sandbox/Dockerfile",
        "images/common/setup-source.sh",
        "runtime/evaluator/main.py",
        "runtime/mcp/server.py",
        "runtime/plugins/plugins.yaml",
        "runtime/plugins/schema.json",
        "sdk/python/pyproject.toml",
        "sdk/python/README.md",
        "sdk/python/sse/__init__.py",
        "datasets/pilot/manifest.json",
        "datasets/pilot/images.lock.json",
        "datasets/pilot/LICENSE",
    } <= files


def test_the_hook_leaves_out_task_folders_and_caches() -> None:
    files = set(hatch_build.data_files(CHECKOUT).values())

    datasets = {f for f in files if f.startswith("datasets/")}
    assert datasets == {"datasets/pilot/manifest.json", "datasets/pilot/images.lock.json", "datasets/pilot/LICENSE"}
    assert [f for f in files if "__pycache__" in f or f.endswith(".pyc") or ".venv" in f] == []
    assert not any(f.startswith(("sdk/daemon/", "runtime/entrypoint/", "webui/")) for f in files)


def test_the_hook_reports_a_missing_entry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hatch_build, "INCLUDE", ("agents",))

    with pytest.raises(FileNotFoundError, match="agents"):
        _ = hatch_build.data_files(tmp_path)


def test_the_wheel_carries_the_assets(wheel: Path) -> None:
    names = wheel_names(wheel)

    expected = {f"{DATA}{name}" for name in hatch_build.data_files(CHECKOUT).values()}
    assert expected <= names
    assert "ssebench/paths.py" in names


def test_a_wheel_built_from_the_tree_has_the_assets(tmp_path: Path) -> None:
    names = wheel_names(build(BENCH, "wheel", tmp_path))

    assert {f"{DATA}{name}" for name in hatch_build.data_files(CHECKOUT).values()} <= names


def test_the_wheel_is_small(wheel: Path) -> None:
    assert wheel.stat().st_size < 1_000_000


def test_the_wheel_has_its_licenses(wheel: Path) -> None:
    names = wheel_names(wheel)

    assert any(n.endswith(".dist-info/licenses/LICENSE") for n in names)
    assert any(n.endswith(".dist-info/licenses/NOTICE") for n in names)


def test_the_wheel_keeps_scripts_executable(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as z:
        mode = z.getinfo(f"{DATA}agents/claude-code/claude-code-sse/run.sh").external_attr >> 16
    assert mode & 0o111


def test_an_installed_wheel_finds_its_home_without_a_checkout(wheel: Path, tmp_path: Path) -> None:
    site = tmp_path / "site-packages"
    with zipfile.ZipFile(wheel) as z:
        z.extractall(site)
    program = (
        "from ssebench import paths\n"
        "print(paths.home())\n"
        "print(paths.is_packaged())\n"
        "print(paths.compose_file().is_file(), (paths.agents_dir() / 'dummy' / 'agent.yaml').is_file())\n"
        "print(paths.default_dataset_dir().joinpath('manifest.json').is_file())\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=tmp_path,
        env={"PYTHONPATH": str(site), "PATH": ""},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [str(site.resolve() / "ssebench" / "_data"), "True", "True True", "True"]


def test_a_build_outside_the_repository_has_no_assets(tmp_path: Path) -> None:
    project = tmp_path / "bench"
    shutil.copytree(BENCH, project, ignore=shutil.ignore_patterns("__pycache__", ".venv", "dist"))

    names = wheel_names(build(project, "wheel", tmp_path / "wheel"))

    assert "ssebench/paths.py" in names
    assert not any(n.startswith(DATA) for n in names)


def test_the_licenses_next_to_the_projects_are_the_repositorys() -> None:
    for project in (BENCH, CHECKOUT / "sdk" / "python"):
        for name in ("LICENSE", "NOTICE"):
            assert (project / name).read_bytes() == (CHECKOUT / name).read_bytes(), f"{project / name}"


@pytest.mark.parametrize("project", [BENCH, CHECKOUT / "sdk" / "python"])
def test_the_metadata_is_complete(project: Path) -> None:
    metadata = tomllib.loads((project / "pyproject.toml").read_text())["project"]

    assert (project / metadata["readme"]).is_file()
    assert metadata["license"] == "Apache-2.0"
    assert metadata["requires-python"] == ">=3.12"
    assert metadata["classifiers"]
    assert set(metadata["urls"]) >= {"Homepage", "Repository", "Issues"}
    assert all(url.startswith("https://github.com/42-b3yond-6ug/ssebench") for url in metadata["urls"].values())
