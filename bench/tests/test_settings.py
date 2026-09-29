from pathlib import Path

import pytest

from ssebench import paths, settings

VARIABLES = ("LITELLM_MASTER_KEY", "POSTGRES_PASSWORD", "LITELLM_PORT", "COMPOSE_PROJECT_NAME")


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _ = (tmp_path / "pyproject.toml").write_text("[tool.ssebench]\n")
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path))
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_reads_dotenv(home: Path) -> None:
    _ = (home / ".env").write_text("# comment\nLITELLM_MASTER_KEY=sk-from-file\nLITELLM_PORT=4100\n")

    assert settings.litellm_master_key() == "sk-from-file"
    assert settings.litellm_port() == 4100


def test_environment_wins_over_dotenv(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = (home / ".env").write_text("COMPOSE_PROJECT_NAME=from-file\n")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "from-env")

    assert settings.compose_project() == "from-env"


def test_defaults_without_dotenv(home: Path) -> None:
    assert settings.dotenv() == {}
    assert settings.litellm_port() == settings.DEFAULT_LITELLM_PORT
    assert settings.compose_project() == settings.DEFAULT_COMPOSE_PROJECT


def test_missing_secret_points_at_setup(home: Path) -> None:
    _ = (home / ".env").write_text("LITELLM_MASTER_KEY=\n")

    with pytest.raises(settings.SettingError, match="just setup"):
        _ = settings.litellm_master_key()


@pytest.mark.parametrize("port", ["http", "0", "70000", "-1"])
def test_rejects_bad_ports(home: Path, monkeypatch: pytest.MonkeyPatch, port: str) -> None:
    monkeypatch.setenv("LITELLM_PORT", port)

    with pytest.raises(settings.SettingError, match="LITELLM_PORT"):
        _ = settings.litellm_port()


def test_no_home_means_no_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path / "missing"))

    assert settings.dotenv() == {}
