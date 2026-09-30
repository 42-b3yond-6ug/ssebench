"""The review takes the agent's patch from the daemon, never from git in the agent's repository."""

from __future__ import annotations

import asyncio
import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

AGENT_PATCH = "--- a/f.c\n+++ b/f.c\n@@ -1 +1 @@\n-bug\n+fix\n"
REFERENCE_PATCH = "--- a/g.c\n+++ b/g.c\n@@ -1 +1 @@\n-bad\n+good\n"


class FakeDaemon:
    connections: list[str | None] = []
    requests: list[str] = []
    final_diff = AGENT_PATCH

    def __init__(self, socket: str | None = None) -> None:
        FakeDaemon.connections.append(socket)

    def get(self, path: str) -> dict[str, str]:
        FakeDaemon.requests.append(path)
        assert path == "/final_diff"
        return {"diff": FakeDaemon.final_diff}


class FakeAgent:
    prompts: list[str] = []

    async def __aenter__(self) -> FakeAgent:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def create_session(self, title: str) -> str:
        return "session"

    async def send_prompt(self, session_id: str, prompt: str) -> Any:
        FakeAgent.prompts.append(prompt)
        return SimpleNamespace(final_message="looks fine", full_log="dialog")


@pytest.fixture
def review(monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """The plugin's module, imported with no daemon: `sse.project` asks for it when it is imported."""
    monkeypatch.setitem(sys.modules, "sse.project", SimpleNamespace(metadata=SimpleNamespace(source=Path("/src"))))
    monkeypatch.setitem(sys.modules, "config", SimpleNamespace(make_opencode_agent=FakeAgent))
    monkeypatch.delitem(sys.modules, "review", raising=False)
    module = importlib.import_module("review")
    yield module
    sys.modules.pop("review", None)


@pytest.fixture(autouse=True)
def fakes(review: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    FakeDaemon.connections, FakeDaemon.requests, FakeDaemon.final_diff = [], [], AGENT_PATCH
    FakeAgent.prompts = []
    monkeypatch.setattr(review, "Daemon", FakeDaemon)
    monkeypatch.setattr(review, "get_reference_patch", lambda: REFERENCE_PATCH)
    monkeypatch.delenv("SSE_ADMIN_SOCKET", raising=False)


def test_the_agent_patch_comes_from_the_admin_socket(review: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SSE_ADMIN_SOCKET", "/run/elsewhere/admin.sock")

    assert review.get_agent_patch() == AGENT_PATCH

    assert FakeDaemon.connections == ["/run/elsewhere/admin.sock"]


def test_the_admin_socket_defaults_to_the_standard_one(review: ModuleType) -> None:
    _ = review.get_agent_patch()

    assert FakeDaemon.connections == ["/run/ssebench/admin.sock"]


def test_the_prompt_carries_both_patches_and_does_not_ask_for_git_diff(review: ModuleType, tmp_path: Path) -> None:
    text = asyncio.run(review.run_review(str(tmp_path)))

    assert text == "looks fine"
    [prompt] = FakeAgent.prompts
    assert AGENT_PATCH in prompt
    assert REFERENCE_PATCH in prompt
    assert "git diff" not in prompt
    assert (tmp_path / "review.txt").read_text() == "looks fine"


def test_no_agent_changes_skip_the_review(review: ModuleType, tmp_path: Path) -> None:
    FakeDaemon.final_diff = "\n"

    assert asyncio.run(review.run_review(str(tmp_path))) is None

    assert FakeAgent.prompts == []
