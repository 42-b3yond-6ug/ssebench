"""The MCP server's difficulty level: an invalid SSE_DIFFICULTY stops it, never defaults."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def load_config() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ssebench_mcp_config", Path(__file__).parents[1] / "config.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


config = load_config()


def test_unset_level_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SSE_DIFFICULTY", raising=False)
    test_config = config.load_mcp_config().test_config
    assert test_config == config.TestConfig.from_difficulty(config.DifficultyLevel.NO_FUTURE_TEST)


@pytest.mark.parametrize("level", range(5))
def test_levels_zero_to_four_are_accepted(monkeypatch: pytest.MonkeyPatch, level: int) -> None:
    monkeypatch.setenv("SSE_DIFFICULTY", str(level))
    test_config = config.load_mcp_config().test_config
    assert test_config == config.TestConfig.from_difficulty(config.DifficultyLevel(level))


@pytest.mark.parametrize("value", ["", "5", "-1", "two", "2.0"])
def test_invalid_levels_are_rejected(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("SSE_DIFFICULTY", value)
    with pytest.raises(ValueError, match="0 to 4"):
        _ = config.load_mcp_config()
