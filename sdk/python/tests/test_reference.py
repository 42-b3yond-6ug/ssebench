"""The reference patch comes from the daemon's admin socket, never the agent-facing one."""

from __future__ import annotations

import pytest

from sse import reference


class FakeDaemon:
    sockets: list[str | None] = []

    def __init__(self, socket: str | None = None):
        FakeDaemon.sockets.append(socket)

    def get(self, path: str) -> dict[str, str]:
        assert path == "/reference/patch"
        return {"diff": "--- a/f\n+++ b/f\n"}


@pytest.fixture(autouse=True)
def fake_daemon(monkeypatch: pytest.MonkeyPatch):
    FakeDaemon.sockets = []
    monkeypatch.setattr(reference, "Daemon", FakeDaemon)
    monkeypatch.setenv("SSE_DAEMON_SOCKET", "/tmp/sse.sock")


def test_uses_the_admin_socket_from_the_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SSE_ADMIN_SOCKET", "/run/elsewhere/admin.sock")
    assert reference.get_reference_patch() == "--- a/f\n+++ b/f\n"
    assert FakeDaemon.sockets == ["/run/elsewhere/admin.sock"]


def test_defaults_to_the_standard_admin_socket(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SSE_ADMIN_SOCKET", raising=False)
    _ = reference.get_reference_patch()
    assert FakeDaemon.sockets == ["/run/ssebench/admin.sock"]
