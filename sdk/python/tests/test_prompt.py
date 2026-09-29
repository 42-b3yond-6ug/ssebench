"""Tests for sse.prompt: the task prompt of the bundled agents."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from sse.metadata import Metadata, TaskDescription
from sse.prompt import build_prompt

PILOT = Path(__file__).resolve().parents[3] / "datasets" / "pilot"
SNAPSHOTS = Path(__file__).parent / "snapshots"


def pilot_metadata(task_id: str) -> Metadata:
    """Return the daemon's public view of a pilot task, read from its folder.

    Report paths in the config are relative to the task's `sse/` folder; its
    Dockerfile copies the scripts from `sse/` to `/ssebench/scripts/`.
    """
    folder = PILOT / task_id / "sse"
    config = yaml.safe_load((folder / "config.yaml").read_text())
    td = config["task_description"]
    scripts = config["scripts"]
    return Metadata(
        id=config["id"],
        project=config["project"],
        language=config["language"],
        source=Path(config["source"]),
        task_description=TaskDescription(
            issue=td.get("issue"),
            crash_report=[(folder / p).read_text() for p in td["crash_report"]],
            bug_description=td.get("bug_description"),
        ),
        poc=[Path("/ssebench") / p for p in config["files"]["poc"]],
        build_script=(folder / Path(scripts["build"]).name).read_text(),
        test_script=(folder / Path(scripts["test"]).name).read_text(),
    )


def metadata(
    issue: str | None = None,
    crash_report: list[str] | None = None,
    bug_description: str | None = None,
    **kwargs: object,
) -> Metadata:
    fields: dict[str, object] = {
        "id": "demo-1",
        "project": "demo",
        "language": "c",
        "source": Path("/src/demo"),
        "poc": [Path("/ssebench/pocs/crash.bin")],
        "build_script": "#!/bin/bash\nmake\n",
        "test_script": "#!/bin/bash\n/ssebench/scripts/build.sh\nmake check\n",
    }
    fields.update(kwargs)
    return Metadata(
        task_description=TaskDescription(issue, crash_report, bug_description),
        **fields,  # pyright: ignore[reportArgumentType]
    )


def test_pilot_task_matches_snapshot() -> None:
    snapshot = SNAPSHOTS / "gjson-196-bf4efcb.prompt.md"
    prompt = build_prompt(pilot_metadata("gjson-196-bf4efcb"))
    if os.environ.get("SSEBENCH_UPDATE_SNAPSHOTS") == "1":
        _ = snapshot.write_text(prompt + "\n")
    assert prompt + "\n" == snapshot.read_text()


def test_names_the_project_and_its_language() -> None:
    prompt = build_prompt(metadata(issue="Overflow.", language="rust"))
    assert "vulnerability in demo, a Rust project" in prompt
    assert "- Name: demo\n- Language: Rust\n- Source code: /src/demo" in prompt


def test_unknown_language_is_shown_as_given() -> None:
    assert "- Language: zig" in build_prompt(metadata(issue="x", language="zig"))


def test_issue_alone_is_the_description() -> None:
    prompt = build_prompt(metadata(issue="Parsing a long header overflows."))
    assert "## Vulnerability\n\n### Issue\n\nParsing a long header overflows." in prompt
    assert "### Report" not in prompt
    assert "no description" not in prompt


def test_bug_description_alone_is_the_description() -> None:
    prompt = build_prompt(metadata(bug_description="Heap overflow in parse()."))
    assert "### Bug description\n\nHeap overflow in parse()." in prompt


def test_every_field_in_a_fixed_order() -> None:
    prompt = build_prompt(
        metadata(
            issue="The issue.",
            crash_report=["first report\n", "second report"],
            bug_description="The bug.",
        )
    )
    headings = [
        "### Bug description\n\nThe bug.",
        "### Issue\n\nThe issue.",
        "### Report 1 of 2\n\n```text\nfirst report\n```",
        "### Report 2 of 2\n\n```text\nsecond report\n```",
    ]
    positions = [prompt.index(h) for h in headings]
    assert positions == sorted(positions)


def test_a_single_report_is_not_numbered() -> None:
    prompt = build_prompt(metadata(crash_report=["only report"]))
    assert "### Report\n\n```text\nonly report\n```" in prompt


@pytest.mark.parametrize("empty", ["", "  \n", "none", "None"])
def test_empty_and_placeholder_fields_are_left_out(empty: str) -> None:
    prompt = build_prompt(
        metadata(issue=empty, crash_report=["the report"], bug_description=empty)
    )
    assert "### Issue" not in prompt
    assert "### Bug description" not in prompt
    assert "### Report\n\n```text\nthe report\n```" in prompt


def test_blank_reports_are_left_out() -> None:
    prompt = build_prompt(metadata(crash_report=["", "the report", " \n"]))
    assert "### Report\n\n```text\nthe report\n```" in prompt


def test_without_any_description_says_so() -> None:
    prompt = build_prompt(metadata(bug_description="none"))
    assert "## Vulnerability\n\nThe task has no description of the vulnerability." in (
        prompt
    )


def test_fence_is_longer_than_backticks_in_the_report() -> None:
    report = "```go\npanic()\n```"
    prompt = build_prompt(metadata(crash_report=[report]))
    assert f"````text\n{report}\n````" in prompt


def test_scripts_are_shown_without_the_hidden_build_script_path() -> None:
    prompt = build_prompt(metadata(issue="x"))
    assert "### Build script\n\n```bash\n#!/bin/bash\nmake\n```" in prompt
    assert "### Test script\n\n```bash\n#!/bin/bash\n# build the project first.\n" in (
        prompt
    )
    assert "/ssebench" not in prompt


def test_without_scripts_there_is_no_build_section() -> None:
    prompt = build_prompt(metadata(issue="x", build_script=None, test_script=None))
    assert "## Build and test" not in prompt


def test_pilot_task_with_a_placeholder_and_a_markdown_report() -> None:
    # bug_description is `none`; the second report is Markdown with code fences.
    prompt = build_prompt(pilot_metadata("yaml-bb4e33b"))
    assert "### Bug description" not in prompt
    assert "### Report 1 of 2\n\n```text\nsignal: killed\n```" in prompt
    assert "### Report 2 of 2\n\n````text\n### Summary\n" in prompt
