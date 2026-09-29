"""An install without a checkout runs from the assets packaged in the wheel.

The wheel carries them as `ssebench/_data/`, laid out like the repository. The fixture builds a
small copy of that layout next to a fake `ssebench` package, with the working directory elsewhere.
"""

import subprocess
from pathlib import Path

import pytest

from ssebench import paths, settings, stack
from ssebench.cli.cli import main
from ssebench.middleware.tools import (
    SandboxToolLayer,
    SidecarToolLayerAgentRuntime,
    SidecarToolLayerEnvironment,
    ToolLayerContext,
    runtime_build_args,
    runtime_image,
)
from ssebench.tasks import catalog

VARIABLES = ("LITELLM_MASTER_KEY", "POSTGRES_PASSWORD", "LITELLM_PORT", "COMPOSE_PROJECT_NAME")


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text)
    return path


def make_checkout(path: Path) -> Path:
    _ = write(path / "pyproject.toml", "[tool.ssebench]\n")
    return path


@pytest.fixture
def packaged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The packaged assets. The working directory is an empty workspace; no environment variable is set."""
    package = tmp_path / "site-packages" / "ssebench"
    data = make_checkout(package / "_data")
    _ = write(data / ".env.example", "LITELLM_MASTER_KEY=\nPOSTGRES_PASSWORD=\nANTHROPIC_API_KEY=\n")
    _ = write(data / "models" / "a.yaml", "- model_name: packaged\n")
    _ = write(data / "images" / "litellm" / "Dockerfile", "FROM scratch\n")
    _ = write(data / "images" / "litellm" / "config_gen.py", "print()\n")
    _ = write(data / "deploy" / "compose" / "docker-compose.yaml", "services: {}\n")
    _ = write(data / "datasets" / "pilot" / "manifest.json", "{}\n")
    _ = write(data / "images" / "sandbox" / "Dockerfile", "FROM scratch\n")
    _ = write(data / "images" / "sidecar-agent" / "Dockerfile", "FROM scratch\n")
    _ = write(data / "images" / "sidecar-case" / "Dockerfile", "FROM scratch\n")

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(paths, "__file__", str(package / "paths.py"))
    monkeypatch.chdir(workspace)
    monkeypatch.delenv(paths.HOME_ENV, raising=False)
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    return data.resolve()


class Docker:
    """Records docker commands, and what the build context held while the command ran."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.context_files: list[str] = []

    def __call__(self, cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(cmd)
        if cmd[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(cmd, 1, "", "No such image")
        if cmd[:3] == ["docker", "buildx", "build"]:
            context = Path(cmd[-1])
            self.context_files = sorted(p.relative_to(context).as_posix() for p in context.rglob("*") if p.is_file())
        return subprocess.CompletedProcess(cmd, 0, "", "")


def test_home_is_the_packaged_assets(packaged: Path) -> None:
    assert paths.home() == packaged
    assert paths.is_packaged()
    assert paths.compose_file() == packaged / "deploy" / "compose" / "docker-compose.yaml"
    assert paths.agents_dir() == packaged / "agents"


def test_a_checkout_wins(packaged: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checkout = make_checkout(tmp_path / "checkout")
    monkeypatch.chdir(checkout)

    assert paths.home() == checkout.resolve()
    assert not paths.is_packaged()
    assert paths.workspace() == checkout.resolve()


def test_the_home_variable_wins(packaged: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "elsewhere"
    home.mkdir()
    monkeypatch.setenv(paths.HOME_ENV, str(home))

    assert paths.home() == home.resolve()
    assert not paths.is_packaged()


def test_the_workspace_is_the_working_directory(packaged: Path) -> None:
    assert paths.workspace() == Path.cwd().resolve()
    assert settings.env_file() == Path.cwd().resolve() / ".env"


def test_dotenv_is_read_from_the_workspace(packaged: Path) -> None:
    _ = write(Path(".env"), "LITELLM_MASTER_KEY=sk-workspace\nLITELLM_PORT=4321\n")

    assert settings.litellm_master_key() == "sk-workspace"
    assert settings.litellm_port() == 4321


def test_models_come_from_the_workspace_when_it_has_them(packaged: Path) -> None:
    assert paths.models_dir() == packaged / "models"

    _ = write(Path("models") / "mine.yaml", "- model_name: mine\n")

    assert paths.models_dir() == Path.cwd().resolve() / "models"


def test_the_bundled_manifest_is_the_packaged_one(packaged: Path) -> None:
    assert catalog.bundled_manifest() == packaged / "datasets" / "pilot" / "manifest.json"


def test_task_folders_need_a_checkout(packaged: Path, caplog: pytest.LogCaptureFixture) -> None:
    with pytest.raises(paths.HomeNotFoundError, match="checkout"):
        _ = paths.require_checkout("The pilot task folders")

    for argv in (["build-case"], ["dataset", "validate"], ["dataset", "schema"]):
        with pytest.raises(SystemExit) as exit_info:
            main(argv)
        assert exit_info.value.code == 1
    assert "needs an SSEBench checkout" in caplog.text


def test_a_checkout_serves_task_folders(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checkout = make_checkout(tmp_path / "checkout")
    monkeypatch.setenv(paths.HOME_ENV, str(checkout))

    assert paths.require_checkout("The pilot task folders") == checkout.resolve()


def test_the_proxy_image_is_built_from_the_workspace_models(packaged: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = write(Path("models") / "mine.yaml", "- model_name: mine\n")
    docker = Docker()
    monkeypatch.setattr(subprocess, "run", docker)

    assert stack.build(stack.config_hash())

    assert docker.context_files == ["images/litellm/Dockerfile", "images/litellm/config_gen.py", "models/mine.yaml"]


def test_the_proxy_image_follows_the_workspace_models(packaged: Path) -> None:
    packaged_models = stack.config_hash()
    _ = write(Path("models") / "mine.yaml", "- model_name: mine\n")
    own_models = stack.config_hash()
    _ = write(Path("models") / "mine.yaml", "- model_name: changed\n")

    assert len({packaged_models, own_models, stack.config_hash()}) == 3


def test_compose_reads_provider_keys_from_the_workspace(packaged: Path) -> None:
    assert stack.compose_env()["SSEBENCH_ENV_FILE"] == str(Path.cwd().resolve() / ".env")


def build_contexts(layer: type, home: Path, monkeypatch: pytest.MonkeyPatch, base: str | None) -> list[str]:
    """The `--build-context` values of the layer's docker build."""
    docker = Docker()
    monkeypatch.setattr(subprocess, "run", docker)
    _ = layer(ToolLayerContext(task_name="demo", source_dir="/src/demo", build_root=home)).docker_image(base)
    [command] = docker.commands
    return [command[i + 1] for i, arg in enumerate(command) if arg == "--build-context"]


LAYERS = [
    (SandboxToolLayer, "case:1"),
    (SidecarToolLayerAgentRuntime, None),
    (SidecarToolLayerEnvironment, "case:1"),
]


@pytest.mark.parametrize(("layer", "base"), LAYERS)
def test_tool_layers_take_the_runtime_from_its_image_without_sources(
    packaged: Path, monkeypatch: pytest.MonkeyPatch, layer: type, base: str | None
) -> None:
    contexts = build_contexts(layer, packaged, monkeypatch, base)

    assert f"runtime=docker-image://{runtime_image()}" in contexts


@pytest.mark.parametrize(("layer", "base"), LAYERS)
def test_tool_layers_build_the_runtime_from_sources_in_a_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layer: type, base: str | None
) -> None:
    home = make_checkout(tmp_path / "checkout")
    for sources in ("sdk/daemon", "runtime/entrypoint"):
        (home / sources).mkdir(parents=True)
    for dockerfile in ("sandbox", "sidecar-agent", "sidecar-case"):
        _ = write(home / "images" / dockerfile / "Dockerfile", "FROM scratch\n")

    contexts = build_contexts(layer, home, monkeypatch, base)

    assert not any(context.startswith("runtime=") for context in contexts)


def test_runtime_image_is_the_published_image_of_this_version() -> None:
    assert runtime_image() == f"{stack.REGISTRY}/runtime:{stack.TAG}"
    assert runtime_build_args(Path("/nonexistent"))[0] == "--build-context"
