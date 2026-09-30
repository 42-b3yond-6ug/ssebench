"""The entrypoint gives the agent the home of `model`, so a bundled wrapper has no reason to set HOME itself."""

import re
from pathlib import Path

import pytest

AGENTS = Path(__file__).resolve().parents[2] / "agents"
WRAPPERS = sorted(AGENTS.glob("*/*-sse/run.sh"))
SETS_HOME = re.compile(r"^\s*(export\s+)?HOME=", re.MULTILINE)


def test_the_bundled_agents_have_wrappers() -> None:
    assert {wrapper.parent.parent.name for wrapper in WRAPPERS} >= {"claude-code", "codex", "opencode"}


@pytest.mark.parametrize("wrapper", WRAPPERS, ids=lambda wrapper: wrapper.parent.parent.name)
def test_a_wrapper_leaves_home_to_the_entrypoint(wrapper: Path) -> None:
    assert not SETS_HOME.search(wrapper.read_text())
