import subprocess
from pathlib import Path

import pytest
import yaml

from ssebench import paths, stack

VARIABLES = ("LITELLM_MASTER_KEY", "POSTGRES_PASSWORD", "LITELLM_PORT", "COMPOSE_PROJECT_NAME")


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _ = (tmp_path / "pyproject.toml").write_text("[tool.ssebench]\n")
    (tmp_path / "models").mkdir()
    _ = (tmp_path / "models" / "a.yaml").write_text("- model_name: a\n")
    (tmp_path / "images" / "litellm").mkdir(parents=True)
    _ = (tmp_path / "images" / "litellm" / "Dockerfile").write_text("FROM scratch\n")
    (tmp_path / "deploy" / "compose").mkdir(parents=True)
    _ = (tmp_path / "deploy" / "compose" / "docker-compose.yaml").write_text("services: {}\n")
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path))
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    return tmp_path


class Docker:
    """Records docker commands instead of running them."""

    def __init__(self, label: str | None) -> None:
        self.label = label
        self.commands: list[list[str]] = []

    def __call__(self, cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(cmd)
        if cmd[:3] == ["docker", "image", "inspect"]:
            if self.label is None:
                return subprocess.CompletedProcess(cmd, 1, "", "No such image")
            return subprocess.CompletedProcess(cmd, 0, f"{self.label}\n", "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def builds(self) -> list[list[str]]:
        return [cmd for cmd in self.commands if cmd[:3] == ["docker", "buildx", "build"]]

    def compose(self) -> list[list[str]]:
        return [cmd for cmd in self.commands if cmd[:2] == ["docker", "compose"]]


def test_config_hash_follows_models(home: Path) -> None:
    before = stack.config_hash()
    _ = (home / "models" / "b.yml").write_text("- model_name: b\n")
    after_new_file = stack.config_hash()
    _ = (home / "models" / "b.yml").write_text("- model_name: c\n")

    assert len({before, after_new_file, stack.config_hash()}) == 3


def test_config_hash_ignores_other_files(home: Path) -> None:
    before = stack.config_hash()
    _ = (home / "models" / "README.md").write_text("notes\n")

    assert stack.config_hash() == before


@pytest.mark.parametrize("label", [None, "", "stale"])
def test_build_when_missing_or_stale(home: Path, monkeypatch: pytest.MonkeyPatch, label: str | None) -> None:
    docker = Docker(label)
    monkeypatch.setattr(subprocess, "run", docker)

    assert stack.build(stack.config_hash())
    [build] = docker.builds()
    assert f"{stack.CONFIG_LABEL}={stack.config_hash()}" in build
    assert build[build.index("--tag") + 1] == stack.image()


def test_no_build_when_current(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    docker = Docker(stack.config_hash())
    monkeypatch.setattr(subprocess, "run", docker)

    assert not stack.build(stack.config_hash())
    assert docker.builds() == []
    assert stack.build(stack.config_hash(), force=True)


def test_up_rebuilds_after_a_model_change(
    home: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _ = (home / ".env").write_text("LITELLM_MASTER_KEY=sk-test\nPOSTGRES_PASSWORD=pw\nCOMPOSE_PROJECT_NAME=mine\n")
    docker = Docker(stack.config_hash())
    _ = (home / "models" / "a.yaml").write_text("- model_name: changed\n")
    monkeypatch.setattr(subprocess, "run", docker)

    with caplog.at_level("INFO"):
        stack.up()

    assert len(docker.builds()) == 1
    assert "models/ changed" in caplog.text
    [up] = docker.compose()
    assert up[up.index("--project-name") + 1] == "mine"
    assert up[-2:] == ["up", "--detach"]


def test_up_needs_the_secrets(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    docker = Docker(None)
    monkeypatch.setattr(subprocess, "run", docker)

    with pytest.raises(stack.settings.SettingError, match="just setup"):
        stack.up()
    assert docker.commands == []


def test_names_follow_the_project_and_port(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert stack.network() == "ssebench_default"
    assert stack.health_url() == "http://localhost:4000/health/liveliness"

    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "other")
    monkeypatch.setenv("LITELLM_PORT", "4100")

    assert stack.network() == "other_default"
    assert stack.host_url() == "http://localhost:4100"
    assert stack.service_url() == "http://litellm:4000"


def test_compose_env_carries_dotenv_and_settings(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = (home / ".env").write_text("POSTGRES_PASSWORD=from-file\nLITELLM_PORT=4200\n")
    monkeypatch.setenv("POSTGRES_PASSWORD", "from-env")

    env = stack.compose_env()

    assert env["POSTGRES_PASSWORD"] == "from-env"
    assert env["LITELLM_PORT"] == "4200"
    assert env["SSEBENCH_REGISTRY"] == stack.REGISTRY


def test_compose_file_is_project_scoped() -> None:
    compose = yaml.safe_load(paths.compose_file().read_text())

    for service in compose["services"].values():
        assert "container_name" not in service
    assert all(not isinstance(v, dict) or "name" not in v for v in (compose.get("volumes") or {}).values())
    assert "networks" not in compose


def test_image_matches_the_compose_file() -> None:
    compose = yaml.safe_load(paths.compose_file().read_text())
    image = compose["services"]["litellm"]["image"].replace("${SSEBENCH_REGISTRY:-ghcr.io/42-b3yond-6ug/ssebench}", "")

    assert stack.image() == f"{stack.REGISTRY}{image}"
