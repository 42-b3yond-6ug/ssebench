"""The text `test_patch` returns: which checks ran, how each ended, and which checks the difficulty level withholds.

The agent must never read more into a result than the checks behind it show. At the default level the PoCs and
the intent tests are withheld, so a passing result says nothing about whether the vulnerability is fixed, and the
text says so instead of calling the patch valid or telling the agent to stop.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from config import TestConfig

BUILD = "build"
POCS = "PoCs"
INTENT_TESTS = "intent tests"
FUNCTIONAL_TESTS = "functional tests"

# Which failed check the headline names when several failed. The checks themselves are listed in run order.
REASON_ORDER = (BUILD, FUNCTIONAL_TESTS, POCS, INTENT_TESTS)

REASONS = {
    BUILD: "The project failed to build. Please reassess the correctness of your patch.",
    FUNCTIONAL_TESTS: (
        "One or more functionality test(s) failed. Please reassess your patch and make "
        "sure it fixes the vulnerability without compromising the program's functionality."
    ),
    POCS: (
        "At least one proof-of-concept (PoC) still triggers the vulnerability. Please "
        "reassess your patch and make sure it fixes the root cause of the vulnerability."
    ),
    INTENT_TESTS: (
        "One or more intent test(s) failed. These tests validate behavior after "
        "the vulnerability fix. Please reassess your patch to ensure it correctly "
        "addresses the vulnerability and aligns with common patterns in the project."
    ),
}

LOG_FOLDER = Path(os.getenv("MCP_LOG_DIR", "/tmp/mcp/logs"))
MAXIMUM_FULL_LOG_WORD_COUNT = 10_000
TRUNCATED_LOG_LINES = 100


@dataclass(frozen=True)
class Check:
    """How one enabled check ended."""

    name: str
    state: Literal["passed", "failed", "not run"]
    detail: str = ""

    def __str__(self) -> str:
        state = "FAILED" if self.state == "failed" else self.state
        return f"- {self.name}: {state}" + (f" ({self.detail})" if self.detail else "")


@dataclass
class PatchResult:
    """The outcome of the checks `test_patch` ran on the agent's tree."""

    config: TestConfig
    pov_total: int

    build_success: bool | None = None
    pov_passed: int = 0
    func_test_success: bool | None = None
    intent_test_success: bool | None = None
    # Output of each check that failed, by check name.
    logs: dict[str, str] = field(default_factory=dict)

    def checks(self) -> list[Check]:
        """The checks the difficulty level enables, in the order they run."""
        config = self.config
        build_failed = config.enable_build and not self.build_success
        checks: list[Check] = []

        def skipped(name: str) -> Check:
            return Check(name, "not run", "the build failed")

        if config.enable_build:
            checks.append(Check(BUILD, "passed" if self.build_success else "failed"))

        if config.enable_security_test:
            if build_failed:
                checks.append(skipped(POCS))
            elif self.pov_total == 0:
                checks.append(Check(POCS, "passed", "the task has none"))
            elif self.pov_passed >= self.pov_total:
                checks.append(Check(POCS, "passed", f"{self.pov_passed} of {self.pov_total}"))
            else:
                detail = (
                    f"passed {self.pov_passed} of {self.pov_total}; stopped at the first that still triggers the bug"
                )
                checks.append(Check(POCS, "failed", detail))

        if config.enable_intent_test:
            if build_failed:
                checks.append(skipped(INTENT_TESTS))
            else:
                checks.append(Check(INTENT_TESTS, "passed" if self.intent_test_success else "failed"))

        if config.enable_function_test:
            if build_failed:
                checks.append(skipped(FUNCTIONAL_TESTS))
            elif config.enable_intent_test and self.intent_test_success:
                # The intent tests include the functional tests, so they are not run again.
                checks.append(Check(FUNCTIONAL_TESTS, "passed", "covered by the intent tests"))
            else:
                checks.append(Check(FUNCTIONAL_TESTS, "passed" if self.func_test_success else "failed"))

        return checks

    def unavailable(self) -> list[str]:
        """The checks the difficulty level withholds from `test_patch`."""
        config = self.config
        names = [
            (config.enable_build, BUILD),
            (config.enable_security_test, POCS),
            (config.enable_intent_test, INTENT_TESTS),
            (config.enable_function_test, FUNCTIONAL_TESTS),
        ]
        return [name for enabled, name in names if not enabled]

    def ok(self) -> bool:
        """Whether every check that ran passed. True when none ran."""
        return all(check.state == "passed" for check in self.checks())

    def __str__(self) -> str:
        """The agent's view of the result."""
        checks = self.checks()
        failed = {check.name for check in checks if check.state == "failed"}
        reason = next((name for name in REASON_ORDER if name in failed), None)
        withheld = self.unavailable()

        sections: list[str] = []

        if reason is not None:
            sections.append(f"test_patch result: FAILED. {REASONS[reason]}")
        elif not checks:
            sections.append("test_patch result: no checks ran.")
        elif withheld:
            sections.append("test_patch result: every check that ran passed.")
        else:
            sections.append("test_patch result: every check passed.")

        if checks:
            sections.append("\n".join(["Checks:", *(str(check) for check in checks)]))

        if withheld:
            difficulty = self.config.difficulty
            note = (
                f"Not available at difficulty level {int(difficulty)} ({difficulty.name}): {', '.join(withheld)}. "
                "Nothing is reported about them."
            )
            if reason is None and not checks:
                note += " test_patch has nothing to run at this level, so this result says nothing about your patch."
            elif reason is None and POCS in withheld:
                note += " Without the PoCs, this result does not show whether the vulnerability is fixed."
            sections.append(note)

        if reason is not None:
            sections.append(self._log_section(reason))

        return "\n\n".join(sections)

    def _log_section(self, name: str) -> str:
        log = self.logs.get(name)
        if log is None:
            return f"Full log ({name}):\nNo log available"

        if len(log.split()) <= MAXIMUM_FULL_LOG_WORD_COUNT:
            return f"Full log ({name}):\n{log}"

        logfile = LOG_FOLDER / f"{uuid.uuid4()}.txt"
        log_saved = False
        try:
            LOG_FOLDER.mkdir(mode=0o755, parents=True, exist_ok=True)
            _ = logfile.write_text(log)
            logfile.chmod(0o644)
            log_saved = True
        except OSError:
            pass  # The agent is told below that the full log is gone.

        # The shorter of the last lines and the last words keeps the result inside the agent's context.
        truncated_by_lines = "\n".join(log.split("\n")[-TRUNCATED_LOG_LINES:])
        truncated_by_words = " ".join(log.split()[-MAXIMUM_FULL_LOG_WORD_COUNT:])
        truncated = truncated_by_lines if len(truncated_by_lines) <= len(truncated_by_words) else truncated_by_words

        if log_saved:
            return f"Truncated log ({name}):\n{truncated}\n\nFull log available at {logfile}"
        return f"Truncated log ({name}):\n{truncated}\n\n(Full log could not be saved due to an internal error)"
