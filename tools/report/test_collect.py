"""Which runs under results/ the report counts: the latest of each task, model and agent, or all of them."""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from collect import collect, find_summaries, main

FIXTURE_RESULTS = Path(__file__).resolve().parent / "fixtures" / "results"
TEMPLATE = next(FIXTURE_RESULTS.glob("gjson-196-bf4efcb/claude-sonnet-4-6/claude-code/*/summary.json"))
START = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def write_run(
    results: Path,
    run_id: str,
    minutes: int | None,
    *,
    task: str = "gjson-196-bf4efcb",
    model: str = "claude-sonnet-4-6",
    agent: str = "claude-code",
    spend: float = 0.0,
) -> Path:
    """A run's summary at its place under `results`, started `minutes` after START; none without a start time."""
    summary: dict[str, Any] = json.loads(TEMPLATE.read_text())
    summary["task"]["id"] = task
    summary["config"].update(model=model, agent=agent)
    summary["spend"] = spend
    summary["run_id"] = run_id
    summary["started_at"] = None if minutes is None else (START + timedelta(minutes=minutes)).isoformat()
    directory = results / task / model / agent / run_id
    directory.mkdir(parents=True)
    _ = (directory / "result.json").write_text("{}")
    _ = (directory / "summary.json").write_text(json.dumps(summary))
    return directory


def ids(records: list[dict[str, Any]]) -> list[str]:
    return [r["run_id"] for r in records]


def test_the_latest_run_is_the_one_that_started_last_whatever_its_id(tmp_path: Path) -> None:
    # A name chosen by the user says nothing about time: the start time decides.
    _ = write_run(tmp_path, "zzz-first", 0, spend=1)
    _ = write_run(tmp_path, "aaa-second", 10, spend=2)
    _ = write_run(tmp_path, "mmm-third", 5, spend=3)

    [record] = collect(tmp_path)

    assert record["run_id"] == "aaa-second" and record["spend"] == 2
    assert record["trial"] == 1 and record["trials"] == 1


def test_a_run_that_started_at_the_same_time_is_ordered_by_its_id(tmp_path: Path) -> None:
    _ = write_run(tmp_path, "a", 0)
    _ = write_run(tmp_path, "b", 0)

    assert ids(collect(tmp_path)) == ["b"]


def test_a_run_without_a_start_time_is_older_than_any_that_has_one(tmp_path: Path) -> None:
    _ = write_run(tmp_path, "z-no-time", None)
    _ = write_run(tmp_path, "a-timed", 0)

    assert ids(collect(tmp_path)) == ["a-timed"]
    assert ids(collect(tmp_path, "all")) == ["z-no-time", "a-timed"]


def test_all_keeps_every_run_in_time_order_and_numbers_the_trials(tmp_path: Path) -> None:
    _ = write_run(tmp_path, "b", 20)
    _ = write_run(tmp_path, "c", 30)
    _ = write_run(tmp_path, "a", 10)

    records = collect(tmp_path, "all")

    assert ids(records) == ["a", "b", "c"]
    assert [(r["trial"], r["trials"]) for r in records] == [(1, 3), (2, 3), (3, 3)]


def test_each_task_model_and_agent_has_its_own_latest_run(tmp_path: Path) -> None:
    _ = write_run(tmp_path, "old", 0)
    _ = write_run(tmp_path, "new", 1)
    _ = write_run(tmp_path, "other-task", 0, task="bluemonday-524f142")
    _ = write_run(tmp_path, "other-model", 0, model="gpt-x")
    _ = write_run(tmp_path, "other-agent", 0, agent="codex")

    records = collect(tmp_path)

    assert sorted((r["task"]["id"], r["config"]["model"], r["config"]["agent"], r["run_id"]) for r in records) == [
        ("bluemonday-524f142", "claude-sonnet-4-6", "claude-code", "other-task"),
        ("gjson-196-bf4efcb", "claude-sonnet-4-6", "claude-code", "new"),
        ("gjson-196-bf4efcb", "claude-sonnet-4-6", "codex", "other-agent"),
        ("gjson-196-bf4efcb", "gpt-x", "claude-code", "other-model"),
    ]
    assert len(collect(tmp_path, "all")) == 5


def test_a_model_name_with_a_provider_prefix_is_found(tmp_path: Path) -> None:
    _ = write_run(tmp_path, "r1", 0, model="openai/gpt-5")

    assert ids(collect(tmp_path)) == ["r1"]


def test_the_run_id_is_taken_from_the_directory(tmp_path: Path) -> None:
    directory = write_run(tmp_path, "the-directory", 0)
    summary = json.loads((directory / "summary.json").read_text())
    summary["run_id"] = "copied-from-elsewhere"
    _ = (directory / "summary.json").write_text(json.dumps(summary))

    assert ids(collect(tmp_path)) == ["the-directory"]


def test_the_latest_link_is_not_a_run_of_its_own(tmp_path: Path) -> None:
    directory = write_run(tmp_path, "r1", 0)
    (directory.parent / "latest").symlink_to("r1")

    assert ids(collect(tmp_path, "all")) == ["r1"]


def test_what_only_looks_like_a_run_is_left_out(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    _ = write_run(tmp_path, "real", 0)
    # A summary that is not in the directory of its task, model and agent.
    copy = write_run(tmp_path, "copy", 0, task="bluemonday-524f142")
    moved = tmp_path / "elsewhere" / "a" / "b" / "c"
    moved.parent.mkdir(parents=True)
    _ = copy.rename(moved)
    # What a dataset verification leaves in results/: its own summary and the runs it made.
    verify = tmp_path / "dataset-verify"
    verify.mkdir()
    _ = (verify / "summary.json").write_text('{"tasks": []}')
    _ = write_run(verify / "runs" / "results", "verify-run", 0)
    # The layout before run directories.
    _ = (tmp_path / "gjson-196-bf4efcb-dummy-none.json").write_text("{}")

    with caplog.at_level(logging.WARNING):
        assert ids(collect(tmp_path, "all")) == ["real"]

    assert "Ignoring 1 summaries in results/*.json" in caplog.text


def test_a_summary_that_does_not_parse_is_skipped_with_a_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _ = write_run(tmp_path, "good", 0)
    broken = write_run(tmp_path, "broken", 1)
    _ = (broken / "summary.json").write_text('{"task": ')

    with caplog.at_level(logging.WARNING):
        assert ids(collect(tmp_path)) == ["good"]

    assert "Skipping" in caplog.text and "broken" in caplog.text


def test_the_files_inside_a_run_are_not_searched(tmp_path: Path) -> None:
    directory = write_run(tmp_path, "r1", 0)
    nested = directory / "archive" / "project" / "results" / "t" / "m" / "a" / "x"
    nested.mkdir(parents=True)
    _ = (nested / "summary.json").write_text("{}")

    assert find_summaries(tmp_path) == [directory / "summary.json"]


def test_no_results_is_no_runs(tmp_path: Path) -> None:
    assert collect(tmp_path / "missing") == []


def test_main_writes_the_combined_json(tmp_path: Path) -> None:
    results = tmp_path / "results"
    _ = write_run(results, "old", 0, spend=1)
    _ = write_run(results, "new", 1, spend=2)
    output = tmp_path / "result.json"

    assert main(["--results", str(results), "--output", str(output)]) == 0
    latest = json.loads(output.read_text())
    assert main(["--results", str(results), "--output", str(output), "--runs", "all"]) == 0
    every = json.loads(output.read_text())

    assert [r["spend"] for r in latest] == [2]
    assert [r["spend"] for r in every] == [1, 2]


def test_main_fails_when_there_is_nothing_to_report(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    assert main(["--results", str(tmp_path), "--output", str(tmp_path / "out.json")]) == 1
    assert "No run summaries" in caplog.text
    assert not (tmp_path / "out.json").exists()
