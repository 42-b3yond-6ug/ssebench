import importlib
import pkgutil
import subprocess
import sys
from pathlib import Path

import pytest

import ssebench

MODULES = sorted(
    info.name
    for info in pkgutil.walk_packages(ssebench.__path__, prefix="ssebench.")
    if info.name != "ssebench.__main__"
)


def test_expected_subpackages_exist() -> None:
    for name in ("agents", "cli", "middleware", "models", "paths", "pipe", "runner", "tasks"):
        assert f"ssebench.{name}" in MODULES


@pytest.mark.parametrize("module", MODULES)
def test_module_imports(module: str) -> None:
    _ = importlib.import_module(module)


def test_help_runs_outside_the_checkout(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ssebench", "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "build-case" in result.stdout
