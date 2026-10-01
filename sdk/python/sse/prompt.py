"""The task prompt that the bundled agents give their model.

:func:`build_prompt` depends only on the task's public metadata, the daemon's
``GET /project``, so every agent that uses it sends the same text for a task.
That view holds the report contents and the build and test scripts, never the
reference patch, the hidden tests or the proofs of concept.
"""

from __future__ import annotations

import re

from sse.metadata import Metadata

__all__ = ["build_prompt", "task_prompt"]

LANGUAGE_NAMES = {
    "c": "C",
    "c++": "C++",
    "cpp": "C++",
    "go": "Go",
    "java": "Java",
    "javascript": "JavaScript",
    "python": "Python",
    "rust": "Rust",
}

# The test script calls the build script by its path in /ssebench, which the
# agent cannot read; the build script is shown on its own instead.
BUILD_SCRIPT_CALL = "/ssebench/scripts/build.sh"

# Task configs use this word to mean that a field has no content.
PLACEHOLDER = "none"

INSTRUCTIONS = """\
## Objective

Deliver a complete, root-cause fix that prevents all inputs from triggering the \
vulnerability or crashing the program, not only the known proof-of-vulnerability \
(PoV) cases.

## Requirements

1. Identify the vulnerability type, trigger conditions, affected code paths, and \
security impact before changing code.
2. Fix the underlying issue at its root cause. Don't patch only symptoms or the PoV. \
Do not "fix" by catch-all swallowing, disabling features, PoV-only special casing, or \
overly broad input bans.
3. Change only the project's code. Do not add, update or delete tests or test data, \
even where a test expects the old behavior: the validation tests are kept separately \
and take care of that. To check your fix, write temporary programs or inputs outside \
the project's source tree.
4. Do not unintentionally break expected behavior. If behavior must change, make it \
explicit and justified.
5. Prefer minimal, clear, idiomatic changes. Avoid hacks, fragile checks, or broad \
refactors unless necessary.
6. Use available tools deliberately. Inspect surrounding code to infer intended \
behavior and constraints.

After the fix is complete, commit your changes with a clear commit message.

## Validation

Your fix will be validated by tests designed by human experts to evaluate the code \
quality:

- running the test suite to confirm no regressions;
- running PoVs to confirm the exploit no longer works (PoVs may not be available to \
you);
- testing security-oriented edge cases beyond the PoV;
- developer review for code quality and alignment with intended functionality."""


def language_name(language: str) -> str:
    return LANGUAGE_NAMES.get(language.lower(), language)


def build_prompt(metadata: Metadata) -> str:
    """Return the task prompt for a task's public metadata.

    The prompt names the project and its language, gives fixed instructions, then
    every description field that is set (the bug description, the issue and each
    report), the source path, and the build and test scripts. A field that is
    empty or holds the placeholder ``none`` is left out.
    """
    language = language_name(metadata.language)
    sections = [
        f"# Task\n\nYou are a software security engineer. Fix a confirmed "
        f"vulnerability in {metadata.project}, a {language} project, by modifying "
        f"its source code.",
        INSTRUCTIONS,
        _vulnerability(metadata),
        f"## Project\n\n- Name: {metadata.project}\n- Language: {language}\n"
        f"- Source code: {metadata.source}",
        _build_and_test(metadata),
    ]
    return "\n\n".join(s for s in sections if s)


def task_prompt() -> str:
    """Return the prompt for the task of this container.

    It imports :mod:`sse.project`, so it needs the daemon.
    """
    from sse.project import metadata

    return build_prompt(metadata)


def _given(text: str | None) -> str | None:
    """Return a description field's text, or None when it has no content."""
    if text is None:
        return None
    text = text.strip()
    return text if text and text.lower() != PLACEHOLDER else None


def _fenced(text: str, info: str) -> str:
    """Put text in a code fence longer than any run of backticks it contains."""
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{info}\n{text}\n{fence}"


def _vulnerability(metadata: Metadata) -> str:
    task = metadata.task_description
    parts = ["## Vulnerability"]
    if bug_description := _given(task.bug_description):
        parts.append(f"### Bug description\n\n{bug_description}")
    if issue := _given(task.issue):
        parts.append(f"### Issue\n\n{issue}")
    reports = [r.rstrip().lstrip("\n") for r in task.crash_report or []]
    reports = [r for r in reports if r.strip()]
    for i, report in enumerate(reports, start=1):
        heading = "Report" if len(reports) == 1 else f"Report {i} of {len(reports)}"
        parts.append(f"### {heading}\n\n{_fenced(report, 'text')}")
    if len(parts) == 1:
        parts.append("The task has no description of the vulnerability.")
    return "\n\n".join(parts)


def _build_and_test(metadata: Metadata) -> str | None:
    parts = ["## Build and test"]
    if metadata.build_script:
        script = metadata.build_script.strip()
        parts.append(f"### Build script\n\n{_fenced(script, 'bash')}")
    if metadata.test_script:
        script = metadata.test_script.replace(
            BUILD_SCRIPT_CALL, "# build the project first."
        ).strip()
        parts.append(f"### Test script\n\n{_fenced(script, 'bash')}")
    return "\n\n".join(parts) if len(parts) > 1 else None
