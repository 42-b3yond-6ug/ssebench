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


def test_run_network_follows_the_egress_policy(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert stack.run_network() == "ssebench_agents"
    assert stack.run_network("restricted") == "ssebench_agents"
    assert stack.run_network("open") == "ssebench_default"

    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "other")
    assert stack.run_network() == "other_agents"

    with pytest.raises(ValueError, match="egress"):
        _ = stack.run_network("anything")


def test_compose_keeps_agents_off_the_internet() -> None:
    compose = yaml.safe_load(paths.compose_file().read_text())
    assert compose["networks"]["agents"]["internal"] is True
    # The proxy must be on both: the internal network for agents, the default one for providers.
    assert set(compose["services"]["litellm"]["networks"]) == {"default", "agents"}


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
    for section in ("volumes", "networks"):
        assert all(not isinstance(v, dict) or "name" not in v for v in (compose.get(section) or {}).values())


def test_image_matches_the_compose_file() -> None:
    compose = yaml.safe_load(paths.compose_file().read_text())
    image = compose["services"]["litellm"]["image"].replace("${SSEBENCH_REGISTRY:-ghcr.io/42-b3yond-6ug/ssebench}", "")

    assert stack.image() == f"{stack.REGISTRY}{image}"


def test_compose_layers_overlays_over_the_base_file(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    docker = Docker(None)
    monkeypatch.setattr(subprocess, "run", docker)
    overlay = home / "deploy" / "compose" / "extra.yaml"

    stack.compose("up", "--detach", overlays=[overlay])
    stack.compose("down")

    [layered, plain] = docker.compose()
    assert [layered[i + 1] for i, arg in enumerate(layered) if arg == "--file"] == [
        str(paths.compose_file()),
        str(overlay),
    ]
    assert [plain[i + 1] for i, arg in enumerate(plain) if arg == "--file"] == [str(paths.compose_file())]
    assert layered[-2:] == ["up", "--detach"]


def test_compose_publishes_the_proxy_on_loopback_unless_told_otherwise() -> None:
    service = yaml.safe_load(paths.compose_file().read_text())["services"]["litellm"]

    assert service["ports"] == ["${LITELLM_BIND:-127.0.0.1}:${LITELLM_PORT:-4000}:4000"]


def test_compose_healthcheck_uses_a_tool_the_image_has() -> None:
    check = yaml.safe_load(paths.compose_file().read_text())["services"]["litellm"]["healthcheck"]["test"]

    assert check[:2] == ["CMD", "python3"]
    assert "wget" not in " ".join(check) and "curl" not in " ".join(check)
    assert "/health/liveliness" in check[-1]


def test_the_published_proxy_image_carries_the_config_label() -> None:
    workflow = (paths.home() / ".github" / "workflows" / "images.yml").read_text()

    assert f'.labels = "{stack.CONFIG_LABEL}=" + $litellm' in workflow


class Containers:
    """Answers `docker ps` and `docker logs` for the stack's services."""

    def __init__(self, states: dict[str, str], logs: dict[str, str]) -> None:
        self.states = states
        self.logs = logs
        self.commands: list[list[str]] = []

    def __call__(self, cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(cmd)
        if cmd[:2] == ["docker", "ps"]:
            service = next(a.split("=", 2)[2] for a in cmd if a.startswith("label=com.docker.compose.service="))
            state = self.states.get(service)
            return subprocess.CompletedProcess(cmd, 0, f"id-{service} {state}\n" if state else "", "")
        if cmd[:2] == ["docker", "logs"]:
            return subprocess.CompletedProcess(cmd, 0, "", self.logs[cmd[-1].removeprefix("id-")])
        return subprocess.CompletedProcess(cmd, 0, "", "")


@pytest.fixture
def unhealthy(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_sleep(seconds: float) -> None:
        raise AssertionError("the wait must end before it sleeps")

    monkeypatch.setattr(stack, "is_healthy", lambda *args, **kwargs: False)
    monkeypatch.setattr(stack.time, "sleep", no_sleep)


def test_wait_fails_at_once_when_the_proxy_exited(home: Path, monkeypatch: pytest.MonkeyPatch, unhealthy: None) -> None:
    docker = Containers(
        {"litellm": "exited", "litellm_db": "running"}, {"litellm": "ImportError: boom\n", "litellm_db": ""}
    )
    monkeypatch.setattr(subprocess, "run", docker)

    with pytest.raises(stack.ProxyError) as error:
        stack.wait_healthy()

    assert "ImportError: boom" in str(error.value)
    assert "POSTGRES_PASSWORD" not in str(error.value)
    assert isinstance(error.value, TimeoutError)


@pytest.mark.parametrize(
    ("proxy_log", "db_log"),
    [
        ("", 'FATAL:  password authentication failed for user "litellm"'),
        ("Authentication failed against database server, the provided database credentials are not valid", ""),
    ],
)
def test_wait_explains_a_stale_database_volume(
    home: Path, monkeypatch: pytest.MonkeyPatch, unhealthy: None, proxy_log: str, db_log: str
) -> None:
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "mine")
    docker = Containers({"litellm": "exited", "litellm_db": "running"}, {"litellm": proxy_log, "litellm_db": db_log})
    monkeypatch.setattr(subprocess, "run", docker)

    with pytest.raises(stack.ProxyError) as error:
        stack.wait_healthy()

    message = str(error.value)
    assert "mine_postgres_data" in message
    assert "`ssebench proxy down --volumes`" in message
    assert "COMPOSE_PROJECT_NAME" in message
    assert all(cmd[-1] != "--follow" for cmd in docker.commands)


def test_wait_names_the_reset_of_the_caller(home: Path, monkeypatch: pytest.MonkeyPatch, unhealthy: None) -> None:
    docker = Containers({"litellm": "exited"}, {"litellm": "P1000: Authentication failed against database"})
    monkeypatch.setattr(subprocess, "run", docker)

    with pytest.raises(stack.ProxyError, match="ssebench demo down"):
        stack.wait_healthy(reset="ssebench demo down")


def test_wait_times_out_while_the_proxy_runs(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stack, "is_healthy", lambda *args, **kwargs: False)
    monkeypatch.setattr(subprocess, "run", Containers({"litellm": "running"}, {}))

    with pytest.raises(stack.ProxyError, match="did not become healthy"):
        stack.wait_healthy(timeout=0)


def test_wait_returns_when_the_proxy_answers(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stack, "is_healthy", lambda *args, **kwargs: True)

    stack.wait_healthy()


def test_down_keeps_the_volume_unless_asked(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = (home / ".env").write_text("LITELLM_MASTER_KEY=sk-test\nPOSTGRES_PASSWORD=pw\n")
    docker = Docker(None)
    monkeypatch.setattr(subprocess, "run", docker)

    stack.down()
    stack.down(volumes=True)

    plain, wiped = docker.compose()
    assert plain[-1:] == ["down"]
    assert wiped[-2:] == ["down", "--volumes"]
