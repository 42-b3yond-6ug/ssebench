from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from dacite import Config, from_dict

from sse import tools
from sse.daemon import Daemon
from sse.helper import ScriptResult


@dataclass
class TaskDescription:
    issue: str | None
    crash_report: list[str] | None
    bug_description: str | None


@dataclass
class Metadata:
    id: str
    project: str
    language: str
    source: Path
    task_description: TaskDescription
    poc: list[Path]
    build_script: str | None = None
    test_script: str | None = None


@dataclass
class Capabilities:
    can_build: bool
    can_run_poc: bool
    poc_count: int
    has_function_test: bool
    has_intent_test: bool


def init_metadata() -> Metadata:
    m = cast(dict[str, Any], Daemon().project())
    return from_dict(Metadata, m, config=Config(cast=[Path]))


def init_capabilities() -> Capabilities:
    data = cast(dict[str, Any], Daemon().capabilities())
    return Capabilities(**data)


metadata = init_metadata()
capabilities = init_capabilities()
source = metadata.source
all_poc = metadata.poc


def build() -> ScriptResult:
    """Build the project. Raises SDKError on infrastructure errors."""
    return tools.bencher.build()


def run_poc(poc: Path) -> ScriptResult:
    """Run a PoC test. Raises SDKError on infrastructure errors."""
    return tools.bencher.run_poc(poc)


def function_test() -> ScriptResult:
    """Run function tests. Raises SDKError on infrastructure errors."""
    return tools.bencher.function_test()


def intent_test() -> ScriptResult:
    """Run intent tests. Raises SDKError on infrastructure errors."""
    return tools.bencher.intent_test()
