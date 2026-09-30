"""`test_patch` runs the checks the difficulty level enables and reports the ones it ran, against a stub project."""

import asyncio
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest
import sse

MCP_DIR = Path(__file__).parents[1]


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"ssebench_mcp_{name}", MCP_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


config = load("config")
patch_report = load("patch_report")


@dataclass
class Script:
    ok: bool
    stdout: str = ""
    stderr: str = ""

    def is_success(self) -> bool:
        return self.ok


class StubProject:
    """Stands in for `sse.project`, which asks the daemon for the task when it is imported."""

    def __init__(self, **failing: str) -> None:
        self.all_poc = [Path("poc1"), Path("poc2")]
        self.failing = failing
        self.calls: list[str] = []

    def _script(self, name: str) -> Script:
        self.calls.append(name)
        if name in self.failing:
            return Script(False, stdout=f"{name} out", stderr=self.failing[name])
        return Script(True)

    def build(self) -> Script:
        return self._script("build")

    def run_poc(self, poc: Path) -> Script:
        return self._script(poc.name)

    def function_test(self) -> Script:
        return self._script("functional")

    def intent_test(self) -> Script:
        return self._script("intent")


def run_test_patch(monkeypatch: pytest.MonkeyPatch, level: int, project: StubProject):
    monkeypatch.setitem(sys.modules, "config", config)
    monkeypatch.setitem(sys.modules, "patch_report", patch_report)
    monkeypatch.setitem(sys.modules, "sse.project", project)
    monkeypatch.setattr(sse, "project", project, raising=False)
    spec = importlib.util.spec_from_file_location("ssebench_mcp_evaluator", MCP_DIR / "evaluator.py")
    assert spec is not None and spec.loader is not None
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    test_config = config.TestConfig.from_difficulty(config.DifficultyLevel(level))
    return asyncio.run(evaluator.test_patch_internal(test_config))


@pytest.mark.parametrize(
    ("level", "calls"),
    [
        (0, ["build", "poc1", "poc2", "intent"]),
        (1, ["build", "poc1", "poc2", "functional"]),
        (2, ["build", "functional"]),
        (3, ["build"]),
        (4, []),
    ],
)
def test_each_level_runs_only_its_checks(monkeypatch: pytest.MonkeyPatch, level: int, calls: list[str]) -> None:
    project = StubProject()
    result = run_test_patch(monkeypatch, level, project)
    assert project.calls == calls
    assert result.ok()
    ran = [line.split(":")[0].removeprefix("- ") for line in str(result).splitlines() if line.startswith("- ")]
    expected = {
        0: ["build", "PoCs", "intent tests", "functional tests"],
        1: ["build", "PoCs", "functional tests"],
        2: ["build", "functional tests"],
        3: ["build"],
        4: [],
    }[level]
    assert ran == expected


def test_a_build_failure_at_level_0_runs_nothing_else(monkeypatch: pytest.MonkeyPatch) -> None:
    project = StubProject(build="compile error")
    result = run_test_patch(monkeypatch, 0, project)
    assert project.calls == ["build"]
    assert not result.ok()
    assert str(result).endswith("Full log (build):\nbuild out\n\ncompile error")


def test_an_unpatched_tree_passes_the_default_level_without_a_claim_of_validity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The PoC would still crash, but the default level withholds it: build and functional tests pass.
    project = StubProject(poc1="AddressSanitizer: heap-buffer-overflow")
    text = str(run_test_patch(monkeypatch, 2, project))
    assert "poc1" not in project.calls
    assert "valid" not in text.lower()
    assert "stop" not in text.lower()
    assert "Not available at difficulty level 2 (NO_FUTURE_TEST): PoCs, intent tests." in text
    assert "does not show whether the vulnerability is fixed" in text


def test_a_poc_failure_stops_the_poc_run_and_the_other_checks_still_run(monkeypatch: pytest.MonkeyPatch) -> None:
    project = StubProject(poc1="crash")
    result = run_test_patch(monkeypatch, 1, project)
    assert project.calls == ["build", "poc1", "functional"]
    assert "- PoCs: FAILED (passed 0 of 2; stopped at the first that still triggers the bug)" in str(result)
    assert "- functional tests: passed" in str(result)
    assert str(result).endswith("Full log (PoCs):\npoc1 out\n\ncrash")


def test_the_intent_tests_passing_covers_the_functional_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    project = StubProject()
    result = run_test_patch(monkeypatch, 0, project)
    assert "functional" not in project.calls
    assert "- functional tests: passed (covered by the intent tests)" in str(result)


def test_the_functional_tests_run_after_the_intent_tests_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    project = StubProject(intent="hidden test failed")
    result = run_test_patch(monkeypatch, 0, project)
    assert project.calls == ["build", "poc1", "poc2", "intent", "functional"]
    assert "- intent tests: FAILED\n- functional tests: passed" in str(result)
    assert str(result).endswith("Full log (intent tests):\nintent out\n\nhidden test failed")
