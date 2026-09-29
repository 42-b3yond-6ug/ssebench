from pathlib import Path

import pytest

from ssebench import paths

# This checkout: bench/tests/ is two levels below the repository root.
CHECKOUT = Path(__file__).resolve().parents[2]


def make_home(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _ = (path / "pyproject.toml").write_text("[tool.ssebench]\n")
    return path


@pytest.fixture(autouse=True)
def no_home_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(paths.HOME_ENV, raising=False)


def test_env_var_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "elsewhere"
    home.mkdir()
    monkeypatch.setenv(paths.HOME_ENV, str(home))
    monkeypatch.chdir(make_home(tmp_path / "checkout"))

    assert paths.home() == home.resolve()


def test_env_var_must_be_a_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path / "missing"))

    with pytest.raises(paths.HomeNotFoundError):
        _ = paths.home()


def test_found_from_a_subdirectory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = make_home(tmp_path / "checkout")
    nested = home / "datasets" / "pilot"
    nested.mkdir(parents=True)
    # A pyproject.toml without the marker table does not stop the search.
    _ = (nested / "pyproject.toml").write_text('[project]\nname = "task"\n')
    monkeypatch.chdir(nested)

    assert paths.home() == home.resolve()


def test_falls_back_to_the_package_location(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert paths.home() == CHECKOUT


def test_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(paths, "__file__", str(tmp_path / "site-packages" / "ssebench" / "paths.py"))

    with pytest.raises(paths.HomeNotFoundError):
        _ = paths.home()


def test_checkout_is_a_home() -> None:
    assert paths.is_home(CHECKOUT)


def test_assets_resolve_inside_the_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(paths.HOME_ENV, str(CHECKOUT))

    assert (paths.agents_dir() / "dummy" / "agent.yaml").is_file()
    assert paths.default_dataset_dir().is_dir()
    assert paths.compose_file().is_file()
