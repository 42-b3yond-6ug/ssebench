"""Combine the run summaries under results/ into the JSON list that main.typ reads.

A run writes results/<task>/<model>/<agent>/<run-id>/summary.json (see ssebench.runner.layout), so
one task, model and agent can have many runs. Which of them the report counts:

  --runs latest  (default) the latest run of each task, model and agent: the one that started last.
  --runs all     every run. Each counts as a sample of its own, so the shares in the summary are
                 shares of runs; a task that ran more than once has a row for each run.

Summaries of the layout before run directories, results/<task>-<agent>-<model>.json, are ignored.
"""

import argparse
import json
import logging
import os
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from ssebench.runner.layout import RESULTS_DIR, SUMMARY_FILE, run_dir
from ssebench.runner.result import PerTaskEvaluationResult

logger = logging.getLogger(__name__)

Selection = Literal["latest", "all"]
NEVER = datetime.min.replace(tzinfo=UTC)
"""The start time of a run whose summary has none, so that it counts as older than every run that has one."""


@dataclass(frozen=True)
class Run:
    task: str
    model: str
    agent: str
    run_id: str
    started_at: datetime
    summary: dict[str, Any]

    @property
    def group(self) -> tuple[str, str, str]:
        return (self.task, self.model, self.agent)

    @property
    def order(self) -> tuple[datetime, str]:
        """What makes a run later than another: its start time, then its ID."""
        return (self.started_at, self.run_id)


def find_summaries(results: Path) -> list[Path]:
    """The `summary.json` of every run directory below `results`, without listing a run's own files."""
    found: list[Path] = []
    for directory, subdirs, files in os.walk(results):
        if SUMMARY_FILE in files:
            found.append(Path(directory) / SUMMARY_FILE)
        if SUMMARY_FILE in files or "result.json" in files:
            subdirs.clear()
    return sorted(found)


def load_run(path: Path, results: Path) -> Run | None:
    """The run that `path` summarizes; None if it is not the summary of a run at its place under `results`.

    The task, model and agent that the summary states must be those of the directories it is in,
    which keeps out what only looks like a run: a copy in another place, or the output of a tool.
    """
    directory = path.parent
    if len(directory.relative_to(results).parts) < 4:
        return None
    try:
        text = path.read_text()
        summary = PerTaskEvaluationResult.model_validate_json(text)
    except (OSError, ValidationError) as e:
        logger.warning(f"Skipping {path}: {e.__class__.__name__}, it is not a run summary")
        return None
    task, model, agent = summary.task.id, summary.config.model, summary.config.agent
    if directory != run_dir(task, agent, model, directory.name, results):
        return None
    return Run(
        task,
        model,
        agent,
        directory.name,
        summary.started_at or NEVER,
        json.loads(text),
    )


def load_runs(results: Path) -> list[Run]:
    runs = [run for path in find_summaries(results) if (run := load_run(path, results)) is not None]
    old = sorted(results.glob("*.json"))
    if old:
        logger.warning(f"Ignoring {len(old)} summaries in results/*.json, the layout before run directories")
    return runs


def select(runs: Sequence[Run], which: Selection = "latest") -> list[Run]:
    """The runs the report counts, in the order task, model, agent, then time."""
    groups: dict[tuple[str, str, str], list[Run]] = defaultdict(list)
    for run in runs:
        groups[run.group].append(run)
    chosen: list[Run] = []
    for group in sorted(groups):
        ordered = sorted(groups[group], key=lambda run: run.order)
        chosen += ordered[-1:] if which == "latest" else ordered
    return chosen


def report_input(runs: Sequence[Run]) -> list[dict[str, Any]]:
    """The summaries, each with its `run_id`, and its `trial` among the `trials` runs that are counted for its group."""
    trials: dict[tuple[str, str, str], int] = defaultdict(int)
    for run in runs:
        trials[run.group] += 1
    seen: dict[tuple[str, str, str], int] = defaultdict(int)
    records: list[dict[str, Any]] = []
    for run in runs:
        seen[run.group] += 1
        records.append({**run.summary, "run_id": run.run_id, "trial": seen[run.group], "trials": trials[run.group]})
    return records


def collect(results: Path, which: Selection = "latest") -> list[dict[str, Any]]:
    """The input of the report for the runs under `results`."""
    runs = load_runs(results)
    chosen = select(runs, which)
    if len(chosen) < len(runs):
        logger.info(f"Read {len(runs)} runs and kept {len(chosen)}: the latest run of each task, model and agent")
    return report_input(chosen)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Combine the run summaries under results/ for the report.")
    parser.add_argument("--results", type=Path, default=Path(RESULTS_DIR), help="Results directory (default: results)")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Write the JSON here (default: stdout)")
    parser.add_argument(
        "--runs",
        choices=("latest", "all"),
        default="latest",
        help="Count the latest run of each task, model and agent, or every run (default: latest)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    records = collect(args.results, args.runs)
    if not records:
        logger.error(f"No run summaries under {args.results}/<task>/<model>/<agent>/<run-id>/{SUMMARY_FILE}")
        return 1
    text = json.dumps(records, indent=2) + "\n"
    if args.output is None:
        _ = sys.stdout.write(text)
    else:
        _ = args.output.write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
