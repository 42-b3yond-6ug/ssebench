from pathlib import Path

import pytest

from ssebench import paths, settings
from ssebench.middleware.tools import (
    RUNTIME_IMAGE_ENV,
    SandboxToolLayer,
    SidecarToolLayerAgentRuntime,
    SidecarToolLayerEnvironment,
    ToolLayer,
    ToolLayerContext,
    runtime_build_args,
    runtime_image,
)

CHECKOUT = Path(__file__).resolve().parents[2]
LAYERS = [
    (SandboxToolLayer, "case:1"),
    (SidecarToolLayerAgentRuntime, None),
    (SidecarToolLayerEnvironment, "case:1"),
]


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(paths.HOME_ENV, str(CHECKOUT))
    monkeypatch.setattr(settings, "dotenv", dict)
    monkeypatch.delenv(RUNTIME_IMAGE_ENV, raising=False)


def test_a_checkout_compiles_the_runtime_by_default() -> None:
    assert runtime_build_args(CHECKOUT) == []


def test_an_image_can_stand_in_for_the_runtime_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RUNTIME_IMAGE_ENV, "registry.test/ssebench/runtime:1.0.0")

    assert runtime_build_args(CHECKOUT) == [
        "--build-context",
        "runtime=docker-image://registry.test/ssebench/runtime:1.0.0",
    ]


def test_the_configured_image_wins_over_the_published_one(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert runtime_build_args(tmp_path) == ["--build-context", f"runtime=docker-image://{runtime_image()}"]

    monkeypatch.setenv(RUNTIME_IMAGE_ENV, "registry.test/ssebench/runtime:1.0.0")

    assert runtime_build_args(tmp_path)[1] == "runtime=docker-image://registry.test/ssebench/runtime:1.0.0"


@pytest.mark.parametrize(("layer", "base"), LAYERS)
def test_every_tool_layer_uses_the_configured_image(
    monkeypatch: pytest.MonkeyPatch, layer: type[ToolLayer], base: str | None
) -> None:
    import subprocess

    commands: list[list[str]] = []
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **kwargs: commands.append(cmd) or subprocess.CompletedProcess(cmd, 0)
    )
    monkeypatch.setenv(RUNTIME_IMAGE_ENV, "registry.test/ssebench/runtime:1.0.0")

    _ = layer(ToolLayerContext(task_name="gjson-196-bf4efcb", source_dir="/src/gjson")).docker_image(base)

    [command] = commands
    contexts = [command[i + 1] for i, arg in enumerate(command) if arg == "--build-context"]
    assert "runtime=docker-image://registry.test/ssebench/runtime:1.0.0" in contexts


@pytest.mark.parametrize(("layer", "base"), LAYERS)
def test_every_tool_layer_builds_for_the_run_platform(
    monkeypatch: pytest.MonkeyPatch, layer: type[ToolLayer], base: str | None
) -> None:
    import subprocess

    commands: list[list[str]] = []
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **kwargs: commands.append(cmd) or subprocess.CompletedProcess(cmd, 0)
    )

    for platform in ("linux/arm64", None):
        context = ToolLayerContext(task_name="gjson-196-bf4efcb", source_dir="/src/gjson", platform=platform)
        _ = layer(context).docker_image(base)

    with_platform, without = commands
    assert [with_platform[i + 1] for i, arg in enumerate(with_platform) if arg == "--platform"] == ["linux/arm64"]
    assert "--platform" not in without
