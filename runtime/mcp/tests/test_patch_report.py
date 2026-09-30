"""What `test_patch` says at every difficulty level: the checks that ran, their outcome, and the checks withheld."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

MCP_DIR = Path(__file__).parents[1]


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"ssebench_mcp_{name}", MCP_DIR / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves string annotations through the module registered in sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


config = load("config")
report = load("patch_report")

LEVELS = range(5)
NAMES = {0: "FULL_ASSISTANCE", 1: "NO_INTENT_TEST", 2: "NO_FUTURE_TEST", 3: "BUILD_ONLY", 4: "NO_BUILD"}


def result_at(level: int, *, pov_total: int = 2, **outcome: Any):
    """The result of a run at `level`; what `outcome` leaves unset is what every check passing would leave."""
    test_config = config.TestConfig.from_difficulty(config.DifficultyLevel(level))
    passing: dict[str, Any] = {
        "build_success": test_config.enable_build or None,
        "pov_passed": pov_total if test_config.enable_security_test else 0,
        "intent_test_success": test_config.enable_intent_test or None,
        "func_test_success": test_config.enable_function_test or None,
    }
    return report.PatchResult(config=test_config, pov_total=pov_total, **{**passing, **outcome})


@pytest.mark.parametrize("level", LEVELS)
def test_a_pass_never_says_valid_or_tells_the_agent_to_stop(level: int) -> None:
    text = str(result_at(level)).lower()
    assert "valid" not in text
    assert "stop" not in text
    assert "succe" not in text


def test_every_check_passing_at_level_0() -> None:
    assert str(result_at(0)) == (
        "test_patch result: every check passed.\n\n"
        "Checks:\n"
        "- build: passed\n"
        "- PoCs: passed (2 of 2)\n"
        "- intent tests: passed\n"
        "- functional tests: passed (covered by the intent tests)"
    )


def test_every_check_passing_at_level_1() -> None:
    assert str(result_at(1)) == (
        "test_patch result: every check that ran passed.\n\n"
        "Checks:\n"
        "- build: passed\n"
        "- PoCs: passed (2 of 2)\n"
        "- functional tests: passed\n\n"
        "Not available at difficulty level 1 (NO_INTENT_TEST): intent tests. Nothing is reported about them."
    )


def test_every_check_passing_at_level_2_does_not_show_the_vulnerability_is_fixed() -> None:
    assert str(result_at(2)) == (
        "test_patch result: every check that ran passed.\n\n"
        "Checks:\n"
        "- build: passed\n"
        "- functional tests: passed\n\n"
        "Not available at difficulty level 2 (NO_FUTURE_TEST): PoCs, intent tests. Nothing is reported about them. "
        "Without the PoCs, this result does not show whether the vulnerability is fixed."
    )


def test_every_check_passing_at_level_3() -> None:
    assert str(result_at(3)) == (
        "test_patch result: every check that ran passed.\n\n"
        "Checks:\n"
        "- build: passed\n\n"
        "Not available at difficulty level 3 (BUILD_ONLY): PoCs, intent tests, functional tests. "
        "Nothing is reported about them. "
        "Without the PoCs, this result does not show whether the vulnerability is fixed."
    )


def test_no_check_runs_at_level_4() -> None:
    assert str(result_at(4)) == (
        "test_patch result: no checks ran.\n\n"
        "Not available at difficulty level 4 (NO_BUILD): build, PoCs, intent tests, functional tests. "
        "Nothing is reported about them. "
        "test_patch has nothing to run at this level, so this result says nothing about your patch."
    )


@pytest.mark.parametrize("level", LEVELS)
def test_the_withheld_checks_are_exactly_those_the_level_disables(level: int) -> None:
    text = str(result_at(level))
    withheld = {
        0: [],
        1: ["intent tests"],
        2: ["PoCs", "intent tests"],
        3: ["PoCs", "intent tests", "functional tests"],
        4: ["build", "PoCs", "intent tests", "functional tests"],
    }[level]
    if not withheld:
        assert "Not available" not in text
        return
    assert f"Not available at difficulty level {level} ({NAMES[level]}): {', '.join(withheld)}." in text
    # A withheld check is never listed as one that ran.
    listed = [line for line in text.splitlines() if line.startswith("- ")]
    assert all(name not in line for line in listed for name in withheld)


@pytest.mark.parametrize("level", [2, 1, 0])
def test_a_failed_functional_test_names_the_check_and_its_log(level: int) -> None:
    kwargs: dict[str, Any] = {"func_test_success": False, "logs": {"functional tests": "FAIL TestFoo"}}
    if level == 0:
        kwargs["intent_test_success"] = False
        kwargs["logs"] = {"functional tests": "FAIL TestFoo", "intent tests": "not this one"}
    text = str(result_at(level, **kwargs))
    assert text.startswith("test_patch result: FAILED. One or more functionality test(s) failed.")
    assert "- functional tests: FAILED" in text
    assert text.endswith("Full log (functional tests):\nFAIL TestFoo")
    assert "valid" not in text.lower()


def test_a_failed_build_at_level_2_skips_the_other_checks() -> None:
    text = str(result_at(2, build_success=False, func_test_success=None, logs={"build": "error: no such file"}))
    assert text == (
        "test_patch result: FAILED. The project failed to build. Please reassess the correctness of your patch.\n\n"
        "Checks:\n"
        "- build: FAILED\n"
        "- functional tests: not run (the build failed)\n\n"
        "Not available at difficulty level 2 (NO_FUTURE_TEST): PoCs, intent tests. Nothing is reported about them.\n\n"
        "Full log (build):\nerror: no such file"
    )


def test_a_failed_build_at_level_0_skips_every_other_check() -> None:
    text = str(
        result_at(
            0,
            build_success=False,
            pov_passed=0,
            intent_test_success=None,
            func_test_success=None,
            logs={"build": "boom"},
        )
    )
    assert "- build: FAILED\n- PoCs: not run (the build failed)\n" in text
    assert "- intent tests: not run (the build failed)\n- functional tests: not run (the build failed)" in text
    assert "Not available" not in text


def test_a_failed_build_at_level_3() -> None:
    text = str(result_at(3, build_success=False, logs={"build": "boom"}))
    assert text.startswith("test_patch result: FAILED. The project failed to build.")
    assert "Checks:\n- build: FAILED\n\n" in text
    assert "Not available at difficulty level 3 (BUILD_ONLY): PoCs, intent tests, functional tests." in text
    assert text.endswith("Full log (build):\nboom")


def test_a_poc_that_still_triggers_the_bug_reports_how_far_the_run_got() -> None:
    text = str(result_at(1, pov_total=3, pov_passed=1, logs={"PoCs": "AddressSanitizer: heap-buffer-overflow"}))
    assert text.startswith(
        "test_patch result: FAILED. At least one proof-of-concept (PoC) still triggers the vulnerability."
    )
    assert "- PoCs: FAILED (passed 1 of 3; stopped at the first that still triggers the bug)" in text
    assert "- functional tests: passed" in text
    assert text.endswith("Full log (PoCs):\nAddressSanitizer: heap-buffer-overflow")


def test_a_task_without_pocs_says_so_at_levels_that_run_them() -> None:
    text = str(result_at(1, pov_total=0, pov_passed=0))
    assert "- PoCs: passed (the task has none)" in text


def test_failed_intent_tests_are_reported_when_the_functional_tests_pass() -> None:
    text = str(result_at(0, intent_test_success=False, logs={"intent tests": "hidden test failed"}))
    assert text.startswith("test_patch result: FAILED. One or more intent test(s) failed.")
    assert "- intent tests: FAILED\n- functional tests: passed\n" in text
    assert text.endswith("Full log (intent tests):\nhidden test failed")


def test_the_headline_names_the_first_failure_in_the_documented_order() -> None:
    text = str(
        result_at(
            0,
            pov_passed=0,
            intent_test_success=False,
            func_test_success=False,
            logs={"PoCs": "poc log", "intent tests": "intent log", "functional tests": "func log"},
        )
    )
    assert text.startswith("test_patch result: FAILED. One or more functionality test(s) failed.")
    assert text.endswith("Full log (functional tests):\nfunc log")


def test_a_failure_without_a_log_says_so() -> None:
    assert str(result_at(2, func_test_success=False)).endswith("Full log (functional tests):\nNo log available")


def test_ok_is_true_when_every_check_that_ran_passed() -> None:
    assert all(result_at(level).ok() for level in LEVELS)
    assert not result_at(2, func_test_success=False).ok()
    assert not result_at(3, build_success=False).ok()
    assert not result_at(1, pov_total=2, pov_passed=1).ok()


def test_a_long_log_is_truncated_and_saved(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(report, "LOG_FOLDER", tmp_path / "logs")
    log = "\n".join(f"line {n} of the build output" for n in range(5000))
    text = str(result_at(3, build_success=False, logs={"build": log}))
    saved = list((tmp_path / "logs").glob("*.txt"))
    assert len(saved) == 1
    assert saved[0].read_text() == log
    assert "Truncated log (build):\n" in text
    assert "line 4999 of the build output" in text
    assert "line 0 of the build output" not in text
    assert text.endswith(f"Full log available at {saved[0]}")


def test_a_long_log_that_cannot_be_saved_says_so(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("")
    monkeypatch.setattr(report, "LOG_FOLDER", blocker / "logs")
    log = "\n".join(f"line {n} of the build output" for n in range(5000))
    text = str(result_at(3, build_success=False, logs={"build": log}))
    assert text.endswith("(Full log could not be saved due to an internal error)")


@pytest.mark.parametrize("level", LEVELS)
def test_the_reference_shows_the_message_of_each_level(level: int) -> None:
    reference = MCP_DIR.parents[1] / "docs" / "reference" / "mcp-server.md"
    if not reference.is_file():
        pytest.skip("the documentation is not part of this checkout")
    assert str(result_at(level)) in reference.read_text()


def test_the_reference_shows_a_failed_build() -> None:
    reference = MCP_DIR.parents[1] / "docs" / "reference" / "mcp-server.md"
    if not reference.is_file():
        pytest.skip("the documentation is not part of this checkout")
    failed = str(result_at(2, build_success=False, func_test_success=None, logs={"build": "<log>"}))
    assert failed in reference.read_text()
