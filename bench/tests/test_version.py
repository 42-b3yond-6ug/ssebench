import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from ssebench import version

CHECKOUT = Path(__file__).resolve().parents[2]


def load_bump() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bump", CHECKOUT / "tools" / "release" / "bump.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("semver", ["0.1.0", "1.0.0", "1.0.0-dev", "1.2.3-alpha.1", "1.2.3-beta.2", "10.0.0-rc.0"])
def test_semver_round_trips_through_pep440(semver: str) -> None:
    assert version.semver(load_bump().pep440(semver)) == semver


@pytest.mark.parametrize("bad", ["1.0", "1.0.0-rc", "1.0.0-rc1", "1.0.0-dev.1", "1.0.0+build", "01.0.0"])
def test_bump_rejects_versions_without_a_pep440_twin(bad: str) -> None:
    with pytest.raises(ValueError):
        load_bump().pep440(bad)


def test_installed_version_matches_the_version_file() -> None:
    assert version.VERSION == (CHECKOUT / "VERSION").read_text().strip()


def test_cli_prints_the_version() -> None:
    result = subprocess.run([sys.executable, "-m", "ssebench", "--version"], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == f"ssebench {version.VERSION}"
