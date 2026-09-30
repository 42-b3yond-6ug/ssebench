"""Render the PDF report from the fixture results, as `just report` does, and read back its tables."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from collect import Selection, collect, find_summaries

from ssebench.runner.result import PerTaskEvaluationResult

REPORT_DIR = Path(__file__).resolve().parent
FIXTURE_RESULTS = REPORT_DIR / "fixtures" / "results"
TYPST = shutil.which("typst")
needs_typst = pytest.mark.skipif(TYPST is None, reason="typst is not installed")


def test_fixtures_match_the_result_schema():
    paths = find_summaries(FIXTURE_RESULTS)
    assert len(paths) == 5
    results = [PerTaskEvaluationResult.model_validate_json(path.read_text()) for path in paths]
    assert any(r.config.reference_run for r in results)
    assert all(r.run_id == path.parent.name and r.started_at for r, path in zip(results, paths, strict=True))


def plain_text(content) -> str:
    """The text of a content element as `typst query` serializes it."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(plain_text(c) for c in content)
    if not isinstance(content, dict):
        return ""
    match content.get("func"):
        case "text" | "symbol":
            return content["text"]
        case "space":
            return " "
        case "smartquote":
            return '"' if content.get("double") else "'"
        case "footnote":
            return ""
    return "".join(plain_text(content[key]) for key in ("body", "children", "child") if key in content)


def table_rows(table: dict) -> list[list[str]]:
    """The cells of a table, header and footer included, as rows of stripped text."""
    cells = []
    for child in table["children"]:
        if child["func"] in ("header", "footer"):
            cells.extend(child["children"])
        else:
            cells.append(child)
    width = len(table["columns"])
    assert len(cells) % width == 0, f"{len(cells)} cells do not fill rows of {width}"
    texts = [plain_text(cell).strip() for cell in cells]
    return [texts[i : i + width] for i in range(0, len(texts), width)]


def render(tmp_path: Path, preset: str, runs: Selection = "latest") -> list[list[list[str]]]:
    """Compile the report in a copy of tools/report and return its tables."""
    report = tmp_path / "report"
    shutil.copytree(REPORT_DIR, report, ignore=shutil.ignore_patterns("fixtures", "__pycache__", "*.py", "*.pdf"))
    # `just report` combines the summaries with tools/report/collect.py.
    (report / "result.json").write_text(json.dumps(collect(FIXTURE_RESULTS, runs)))

    assert TYPST is not None
    args = ["--input", f"preset={preset}"]
    subprocess.run([TYPST, "compile", "main.typ", *args], cwd=report, check=True, capture_output=True, text=True)
    assert (report / "main.pdf").stat().st_size > 0
    query = subprocess.run(
        [TYPST, "query", "main.typ", "table", *args], cwd=report, check=True, capture_output=True, text=True
    )
    return [table_rows(table) for table in json.loads(query.stdout)]


@needs_typst
def test_report_leaves_reference_runs_out_of_the_scores(tmp_path: Path):
    summary, *task_tables = render(tmp_path, "default")

    assert summary == [
        ["Model", "Agent", "Spend", "Time", "Build", "PoC", "Func", "Intent"],
        ["claude-sonnet-4-6", "claude-code", "$0.76", "10 min", "100%", "50%", "50%", "50%"],
    ]
    # One table per model and agent: the reference run has none.
    assert task_tables == [
        [
            ["ID", "Spend", "Time", "Build", "PoC", "Func", "Intent"],
            ["bluemonday-524f142", "$1.10", "15m", "Pass", "0 / 1", "Fail", "Fail"],
            ["gjson-196-bf4efcb", "$0.42", "5m", "Pass", "1 / 1", "Pass", "Pass"],
            ["Avg", "$0.76", "10m", "100%", "50%", "50%", "50%"],
        ]
    ]


@needs_typst
def test_report_lists_runs_that_ended_in_an_error_instead_of_scoring_them(tmp_path: Path):
    summary, *_ = render(tmp_path, "default")
    # The scores have no row for the model that never answered.
    assert [row[0] for row in summary[1:]] == ["claude-sonnet-4-6"]

    assert TYPST is not None
    query = subprocess.run(
        [TYPST, "query", "main.typ", "list"], cwd=tmp_path / "report", check=True, capture_output=True, text=True
    )
    [item] = [plain_text(item).strip() for item in json.loads(query.stdout)]
    assert item.startswith("gjson-196-bf4efcb, gpt-5.2, codex: The agent exited with status 1")


@needs_typst
def test_anonymous_report_hides_the_task_ids(tmp_path: Path):
    _, task_table = render(tmp_path, "anonymous")

    ids = [row[0] for row in task_table[1:-1]]
    assert len(ids) == 2
    assert all(re.fullmatch(r"[0-9a-f]{6}", task_id) for task_id in ids), ids


@needs_typst
def test_report_of_every_run_counts_each_trial_as_a_sample(tmp_path: Path):
    summary, *task_tables = render(tmp_path, "default", "all")

    # gjson ran twice: the first trial failed every check but the build, the latest one passed all.
    assert summary == [
        ["Model", "Agent", "Spend", "Time", "Build", "PoC", "Func", "Intent"],
        ["claude-sonnet-4-6", "claude-code", "$0.71", "13.3 min", "100%", "33.3%", "33.3%", "33.3%"],
    ]
    assert task_tables == [
        [
            ["ID", "Spend", "Time", "Build", "PoC", "Func", "Intent"],
            ["bluemonday-524f142", "$1.10", "15m", "Pass", "0 / 1", "Fail", "Fail"],
            ["gjson-196-bf4efcb #1", "$0.60", "20m", "Pass", "0 / 1", "Fail", "Fail"],
            ["gjson-196-bf4efcb #2", "$0.42", "5m", "Pass", "1 / 1", "Pass", "Pass"],
            ["Avg", "$0.71", "13.3m", "100%", "33.3%", "33.3%", "33.3%"],
        ]
    ]
