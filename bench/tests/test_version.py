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


CHART = "deploy/helm/ssebench/Chart.yaml"


def chart_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> tuple[ModuleType, Path]:
    bump = load_bump()
    chart = tmp_path / CHART
    chart.parent.mkdir(parents=True)
    _ = chart.write_text(text)
    monkeypatch.setattr(bump, "ROOT", tmp_path)
    return bump, chart


def test_the_chart_carries_the_version_as_its_version_and_app_version() -> None:
    bump = load_bump()

    found = {field.label: field.read() for field in bump.chart_fields()}

    assert found == {"version": bump.read_version(), "appVersion": bump.read_version()}


def test_bump_rewrites_the_chart_and_keeps_the_rest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bump, chart = chart_in(
        tmp_path,
        monkeypatch,
        "name: ssebench\nversion: 1.0.0-dev\nappVersion: \"1.0.0-dev\" # the images\nkubeVersion: '>=1.28.0-0'\n",
    )

    for field in bump.chart_fields():
        assert field.write is not None
        field.write(field.expected("1.2.0-rc.1"))

    assert chart.read_text() == (
        "name: ssebench\nversion: 1.2.0-rc.1\nappVersion: 1.2.0-rc.1 # the images\nkubeVersion: '>=1.28.0-0'\n"
    )


def test_check_reports_a_chart_that_is_not_at_the_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bump, _ = chart_in(tmp_path, monkeypatch, "version: 1.0.0-dev\nappVersion: 0.9.0\n")

    problems = [
        f"{field.label} is {field.read()!r}, expected {field.expected('1.0.0-dev')!r}"
        for field in bump.chart_fields()
        if field.read() != field.expected("1.0.0-dev")
    ]

    assert problems == ["appVersion is '0.9.0', expected '1.0.0-dev'"]
