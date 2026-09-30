"""The oracle plugin tells the entrypoint why it skips itself."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

MAIN = Path(__file__).resolve().parents[1] / "main.py"


@pytest.fixture
def main() -> ModuleType:
    spec = importlib.util.spec_from_file_location("oracle_main", MAIN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SSE_API_KEY", "SSE_BASE_URL", "SSE_MODEL_NAME", "SSE_PLUGIN_SKIP_FILE"):
        monkeypatch.delenv(name, raising=False)


def test_without_a_model_it_writes_the_reason_to_the_skip_file(
    main: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    skip = tmp_path / "skip"
    monkeypatch.setenv("SSE_PLUGIN_SKIP_FILE", str(skip))
    monkeypatch.setenv("SSE_MODEL_NAME", "m")

    assert main.main() == 0

    assert skip.read_text().strip() == "No LLM configured (SSE_API_KEY, SSE_BASE_URL unset)"


def test_without_a_model_it_skips_even_when_no_skip_file_is_given(main: ModuleType) -> None:
    assert main.main() == 0


def test_with_a_model_it_does_not_write_the_skip_file(
    main: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    skip = tmp_path / "skip"
    monkeypatch.setenv("SSE_PLUGIN_SKIP_FILE", str(skip))
    for name in main.LLM_VARS:
        monkeypatch.setenv(name, "x")

    assert main.llm_ready()
    assert not skip.exists()
