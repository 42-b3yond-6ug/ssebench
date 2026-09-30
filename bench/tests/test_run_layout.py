"""Where the files of a run go: one directory for each run under results/<task>/<model>/<agent>/."""

import logging
import re
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from ssebench.runner.layout import LATEST, group_dir, mark_latest, new_run_id, run_dir, summary_path


def test_the_paths_follow_task_model_agent_and_run() -> None:
    assert group_dir("t-1", "dummy", "m") == Path("results/t-1/m/dummy")
    assert run_dir("t-1", "dummy", "m", "r1") == Path("results/t-1/m/dummy/r1")
    assert summary_path("t-1", "dummy", "m", "r1") == Path("results/t-1/m/dummy/r1/summary.json")


def test_a_model_name_with_a_provider_prefix_makes_nested_directories() -> None:
    assert run_dir("t-1", "dummy", "openai/gpt-5", "r1", Path("/w/results")) == Path(
        "/w/results/t-1/openai/gpt-5/dummy/r1"
    )


def test_two_runs_have_two_directories() -> None:
    assert run_dir("t-1", "dummy", "m", "a") != run_dir("t-1", "dummy", "m", "b")
    assert run_dir("t-1", "dummy", "m", "a").parent == run_dir("t-1", "dummy", "m", "b").parent


def test_a_generated_run_id_is_the_utc_start_time_and_six_hex_digits() -> None:
    now = datetime(2026, 9, 29, 15, 30, 12, tzinfo=timezone(timedelta(hours=-5)))

    assert re.fullmatch(r"20260929-203012-[0-9a-f]{6}", new_run_id(now))
    assert re.fullmatch(r"\d{8}-\d{6}-[0-9a-f]{6}", new_run_id())


def test_generated_run_ids_are_unique_and_sort_by_time() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    ids = [new_run_id(start + timedelta(seconds=n * 1000)) for n in range(5)]

    assert ids == sorted(ids)
    assert len({new_run_id(start) for _ in range(50)}) == 50


def test_latest_follows_the_newest_run(tmp_path: Path) -> None:
    group = tmp_path / "group"
    for name in ("a", "b"):
        (group / name).mkdir(parents=True)
        (group / name / "result.json").write_text(name)

    mark_latest(group / "a")
    assert (group / LATEST).readlink() == Path("a")
    mark_latest(group / "b")

    assert (group / LATEST).readlink() == Path("b")
    assert (group / LATEST / "result.json").read_text() == "b"
    assert sorted(p.name for p in group.iterdir()) == ["a", "b", LATEST]


def test_latest_is_relative_so_the_results_can_be_moved(tmp_path: Path) -> None:
    (tmp_path / "old" / "run").mkdir(parents=True)
    mark_latest(tmp_path / "old" / "run")

    (tmp_path / "old").rename(tmp_path / "new")

    assert (tmp_path / "new" / LATEST).resolve() == tmp_path / "new" / "run"


def test_failing_to_point_latest_is_a_warning_not_an_error(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    group = tmp_path / "group"
    (group / "run").mkdir(parents=True)
    (group / LATEST).mkdir()  # not a link, so it cannot be replaced by one
    (group / LATEST / "keep").write_text("x")

    with caplog.at_level(logging.WARNING):
        mark_latest(group / "run")

    assert "Could not point" in caplog.text
    assert (group / LATEST / "keep").read_text() == "x"
    assert not [p for p in group.iterdir() if p.name.startswith(f".{LATEST}.")]
