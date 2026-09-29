"""Unit tests for the SDK and daemon version check."""

from __future__ import annotations

import logging

import pytest

from sse import daemon


@pytest.mark.parametrize(
    ("sdk_version", "daemon_version"),
    [
        ("1.0.0", "1.0.0"),
        ("1.0.0.dev0", "1.0.0-dev"),
        ("1.0.0a2", "1.0.0-alpha.2"),
        ("1.0.0b1", "1.0.0-beta.1"),
        ("1.0.0rc1", "1.0.0-rc.1"),
    ],
)
def test_same_release_in_both_spellings(sdk_version, daemon_version):
    assert daemon.same_version(sdk_version, daemon_version)


@pytest.mark.parametrize("daemon_version", ["1.0.1", "1.0.0-rc.1", "dev", None])
def test_different_or_unparsable_versions(daemon_version):
    assert not daemon.same_version("1.0.0", daemon_version)


class FakeResponse:
    def __init__(self, version):
        self.version = version

    def json(self):
        return {"version": self.version}


class FakeSession:
    def __init__(self, version):
        self.version = version

    def get(self, url, headers=None):
        return FakeResponse(self.version)


def connect(monkeypatch, daemon_version):
    monkeypatch.setattr(daemon, "__version__", "1.0.0rc1")
    monkeypatch.setenv("SSE_AGENT_DOCKER", "daemon:4263")
    monkeypatch.delenv("SSE_DAEMON_SOCKET", raising=False)
    monkeypatch.setattr(daemon.requests, "Session", lambda: FakeSession(daemon_version))
    return daemon.Daemon()


def test_no_warning_when_versions_match(monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger=daemon.__name__):
        connect(monkeypatch, "1.0.0-rc.1")
    assert caplog.records == []


def test_warns_on_mismatch(monkeypatch, caplog):
    with caplog.at_level(logging.WARNING, logger=daemon.__name__):
        connect(monkeypatch, "1.0.0-rc.2")
    assert "does not match daemon version" in caplog.text
