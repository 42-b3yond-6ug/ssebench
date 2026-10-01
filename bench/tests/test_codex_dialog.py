"""The codex wrapper turns the events of `codex exec --json` into dialog.jsonl entries."""

import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
# Trimmed from a real run (jq_gh_3196): commands that finish out of order, a
# failing command, a file change and the final usage.
STREAM = Path(__file__).parent / "fixtures" / "codex_exec_stream.jsonl"

spec = importlib.util.spec_from_file_location("codex_dialog", ROOT / "agents/codex/codex-sse/dialog.py")
assert spec and spec.loader
codex_dialog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(codex_dialog)


def run(events: list[dict[str, Any]], tmp_path: Path, return_code: int = 0) -> list[dict[str, Any]]:
    path = tmp_path / "archive" / "dialog.jsonl"
    dialog = codex_dialog.DialogWriter(str(path))
    dialog.write_init(task="t", cwd="/src", model="m")
    dialog.write_prompt("fix it")
    for event in events:
        dialog.process_codex_event(event)
    dialog.finish(return_code)
    dialog.close()
    return [json.loads(line) for line in path.read_text().splitlines()]


def fixture_events() -> list[dict[str, Any]]:
    return [json.loads(line) for line in STREAM.read_text().splitlines()]


def test_a_recorded_run_becomes_a_well_formed_dialog(tmp_path: Path) -> None:
    entries = run(fixture_events(), tmp_path)

    assert [e["seq"] for e in entries] == list(range(len(entries)))
    assert [e["type"] for e in entries[:2]] == ["init", "prompt"]
    assert entries[-1]["type"] == "complete"
    assert entries[-1]["status"] == "success"
    assert entries[-1]["turns"] == 1
    assert entries[-1]["total_tokens"] == {"in": 450751, "out": 3299}
    assert [e["content"] for e in entries if e["type"] == "message"][0].startswith("I’ll trace")

    tools = [e for e in entries if e["type"] == "tool"]
    starts = {e["tool_id"]: e for e in tools if e["status"] == "running"}
    results = {e["tool_id"]: e for e in tools if e["status"] != "running"}
    # Every start has exactly one result, whatever order they finish in.
    assert starts.keys() == results.keys() == {"item_1", "item_6", "item_7", "item_8"}
    assert len(tools) == 8

    assert starts["item_1"]["name"] == "bash"
    assert starts["item_1"]["args"]["command"].startswith("/bin/bash -lc")
    # A non-zero exit is an error that keeps the output and names the code.
    assert results["item_1"]["status"] == "error"
    assert results["item_1"]["error"].endswith("[exit code 2]")
    assert results["item_8"]["status"] == "success"
    assert results["item_8"]["result"]

    assert starts["item_6"]["name"] == "file_change"
    assert starts["item_6"]["args"]["changes"][0]["path"] == "/src/jq/src/jv.c"
    assert results["item_6"]["result"] == "update /src/jq/src/jv.c\nupdate /src/jq/tests/jq.test"


def test_reasoning_mcp_calls_searches_and_todo_lists(tmp_path: Path) -> None:
    mcp = {"id": "m", "type": "mcp_tool_call", "server": "ssebench", "tool": "test_patch"}
    events: list[dict[str, Any]] = [
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "r", "type": "reasoning", "text": "think"}},
        {"type": "item.started", "item": {**mcp, "arguments": {"x": 1}, "status": "in_progress"}},
        {
            "type": "item.completed",
            "item": {**mcp, "arguments": {"x": 1}, "result": {"content": [{"type": "text", "text": "ok"}]}},
        },
        {
            "type": "item.completed",
            "item": {"id": "e", "type": "mcp_tool_call", "server": "s", "tool": "t", "error": {"message": "boom"}},
        },
        {"type": "item.completed", "item": {"id": "w", "type": "web_search", "query": "cve"}},
        {"type": "item.updated", "item": {"id": "td", "type": "todo_list", "items": []}},
        {
            "type": "item.completed",
            "item": {"id": "td", "type": "todo_list", "items": [{"text": "a", "completed": True}]},
        },
    ]
    entries = run(events, tmp_path)

    assert [e["type"] for e in entries].count("thinking") == 1
    results = {e["tool_id"]: e for e in entries if e["type"] == "tool" and e["status"] != "running"}
    assert results["m"]["name"] == "mcp__ssebench__test_patch"
    assert results["m"]["result"] == "ok"
    assert results["e"]["error"] == "boom"
    assert results["td"]["result"] == "[x] a"
    # An item first seen as completed still gets its start entry.
    for tool_id in ("m", "e", "w", "td"):
        assert [e["status"] for e in entries if e.get("tool_id") == tool_id][0] == "running"
        assert sum(1 for e in entries if e.get("tool_id") == tool_id) == 2


def test_unknown_events_are_skipped(tmp_path: Path) -> None:
    events: list[dict[str, Any]] = [
        {"type": "thread.started", "thread_id": "x"},
        {"type": "something.new"},
        {"type": "item.completed", "item": {"id": "z", "type": "hologram"}},
        {"type": "item.completed", "item": "not a dict"},
        {"type": "turn.completed"},
        {},
    ]
    entries = run(events, tmp_path)
    assert [e["type"] for e in entries] == ["init", "prompt", "complete"]


def test_a_failed_turn_or_exit_makes_the_dialog_an_error(tmp_path: Path) -> None:
    failed = run(
        [
            {"type": "turn.started"},
            {"type": "error", "message": "retrying"},
            {"type": "turn.failed", "error": {"message": "no quota"}},
        ],
        tmp_path,
    )
    assert failed[-1]["status"] == "error"
    assert failed[-1]["message"] == "no quota"

    crashed = run([{"type": "turn.started"}], tmp_path, return_code=3)
    assert crashed[-1]["status"] == "error"
    assert "3" in crashed[-1]["message"]


def test_a_tool_left_running_is_closed_before_complete(tmp_path: Path) -> None:
    entries = run(
        [{"type": "item.started", "item": {"id": "c", "type": "command_execution", "command": "sleep 9"}}],
        tmp_path,
        return_code=1,
    )
    assert [(e["type"], e.get("status")) for e in entries[2:]] == [
        ("tool", "running"),
        ("tool", "error"),
        ("complete", "error"),
    ]


def test_a_dialog_that_cannot_be_written_does_not_raise(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("")
    dialog = codex_dialog.DialogWriter(str(blocker / "dialog.jsonl"))
    dialog.write_init(task="t", cwd="/", model="m")
    for event in fixture_events():
        dialog.process_codex_event(event)
    dialog.finish(0)
    dialog.close()
