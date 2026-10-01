import json
import os
import sys
import time
from datetime import UTC, datetime
from io import TextIOWrapper
from pathlib import Path
from typing import Any

# =============================================================================
# Dialog Writer - Converts `codex exec --json` events to SSEBench dialog format
# (docs/reference/dialog-protocol.md)
# =============================================================================


def _log(message: str):
    print(f"[codex] dialog: {message}", file=sys.stderr, flush=True)


class DialogWriter:
    """
    Writes agent dialog entries to $SSE_ARCHIVE/dialog.jsonl for WebUI consumption.

    The dialog is a side record: a failure to write it is logged and never
    raised, so it cannot fail the agent run.
    """

    def __init__(self, log_path: str | None = None):
        if log_path is None:
            archive = os.environ.get("SSE_ARCHIVE", "/tmp/sse-archive")
            log_path = f"{archive}/dialog.jsonl"
        self.log_path: Path = Path(log_path)
        self.seq: int = 0
        self.start_time: float = time.time()
        self.turns: int = 0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.pending_tools: dict[str, str] = {}  # tool_id -> tool name
        self.completed: bool = False
        # Set by a turn.failed event; decides the status of the complete entry.
        self.failure: str | None = None
        self.file: TextIOWrapper | None = None
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.file = open(self.log_path, "w")
        except OSError as e:
            _log(f"cannot open {self.log_path}: {e}")

    def _write_entry(self, entry: dict[str, Any]):
        if self.file is None:
            return
        try:
            _ = self.file.write(json.dumps(entry) + "\n")
            self.file.flush()
        except (OSError, ValueError, TypeError) as e:
            _log(f"cannot write {self.log_path}: {e}")

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    def _next_seq(self) -> int:
        seq = self.seq
        self.seq += 1
        return seq

    def write_init(self, task: str, cwd: str, model: str, agent: str = "codex"):
        self._write_entry(
            {
                "seq": self._next_seq(),
                "ts": self._now(),
                "type": "init",
                "data": {"task": task, "cwd": cwd, "model": model, "agent": agent},
            }
        )

    def write_prompt(self, content: str):
        self._write_entry(
            {
                "seq": self._next_seq(),
                "ts": self._now(),
                "type": "prompt",
                "content": content,
            }
        )

    def write_message(self, content: str):
        self._write_entry(
            {
                "seq": self._next_seq(),
                "ts": self._now(),
                "type": "message",
                "role": "assistant",
                "content": content,
            }
        )

    def write_thinking(self, content: str):
        self._write_entry(
            {
                "seq": self._next_seq(),
                "ts": self._now(),
                "type": "thinking",
                "content": content,
            }
        )

    def write_tool_start(
        self, tool_id: str, name: str, args: dict[str, Any] | None = None
    ):
        entry: dict[str, Any] = {
            "seq": self._next_seq(),
            "ts": self._now(),
            "type": "tool",
            "tool_id": tool_id,
            "name": name,
            "status": "running",
        }
        if args:
            entry["args"] = args
        self._write_entry(entry)
        self.pending_tools[tool_id] = name

    def write_tool_result(
        self, tool_id: str, result: str | None = None, error: str | None = None
    ):
        name = self.pending_tools.pop(tool_id, "unknown")
        entry: dict[str, Any] = {
            "seq": self._next_seq(),
            "ts": self._now(),
            "type": "tool",
            "tool_id": tool_id,
            "name": name,
            "status": "error" if error else "success",
        }
        if result:
            entry["result"] = result
        if error:
            entry["error"] = error
        self._write_entry(entry)

    def write_complete(self, status: str = "success", message: str | None = None):
        """Write the final entry. Guarded against double-writes."""
        if self.completed:
            return
        self.completed = True
        # The web UI shows a tool without a result as still running.
        for tool_id in list(self.pending_tools):
            self.write_tool_result(tool_id, error="The agent ended before it finished")
        entry: dict[str, Any] = {
            "seq": self._next_seq(),
            "ts": self._now(),
            "type": "complete",
            "status": status,
            "turns": self.turns,
            "duration_ms": int((time.time() - self.start_time) * 1000),
            "total_tokens": {
                "in": self.total_input_tokens,
                "out": self.total_output_tokens,
            },
        }
        if message:
            entry["message"] = message
        self._write_entry(entry)

    def finish(self, return_code: int):
        """Write the complete entry once the codex process has exited."""
        if self.failure is not None:
            self.write_complete("error", message=self.failure)
        elif return_code != 0:
            self.write_complete(
                "error", message=f"Process exited with code {return_code}"
            )
        else:
            self.write_complete("success")

    def process_codex_event(self, event: dict[str, Any]):
        """
        Convert one `codex exec --json` event. Unknown events and item types
        are skipped.

        - turn.started: counts a turn
        - turn.completed: adds the usage to the totals
        - turn.failed: makes the complete entry an error
        - item.started / item.completed: messages, reasoning and tool calls

        `error` events are retry notices as often as failures, so only
        turn.failed (or the exit code) makes the run an error.
        """
        event_type = event.get("type")

        if event_type == "turn.started":
            self.turns += 1

        elif event_type == "turn.completed":
            usage = event.get("usage") or {}
            self.total_input_tokens += int(usage.get("input_tokens") or 0)
            self.total_output_tokens += int(usage.get("output_tokens") or 0)

        elif event_type == "turn.failed":
            error = event.get("error") or {}
            self.failure = str(error.get("message") or "Turn failed")

        elif event_type in ("item.started", "item.completed"):
            item = event.get("item")
            if isinstance(item, dict):
                self._process_item(event_type == "item.completed", item)

    def _process_item(self, done: bool, item: dict[str, Any]):
        item_type = item.get("type")
        item_id = str(item.get("id") or self._next_seq())

        if item_type == "agent_message":
            if done and item.get("text"):
                self.write_message(item["text"])
            return

        if item_type == "reasoning":
            if done and item.get("text"):
                self.write_thinking(item["text"])
            return

        if item_type == "command_execution":
            name, args = "bash", {"command": item.get("command", "")}
        elif item_type == "file_change":
            name, args = "file_change", {"changes": item.get("changes", [])}
        elif item_type == "mcp_tool_call":
            server = item.get("server", "unknown")
            name = f"mcp__{server}__{item.get('tool', 'unknown')}"
            args = item.get("arguments")
        elif item_type == "web_search":
            name, args = "web_search", {"query": item.get("query", "")}
        elif item_type == "todo_list":
            # Started and updated events repeat the list; the completed one is final.
            if not done:
                return
            name, args = "todo_list", {"items": item.get("items", [])}
        else:
            return

        # An item first seen as completed still gets its start entry, which
        # is what the web UI pairs the result with.
        if item_id not in self.pending_tools:
            self.write_tool_start(
                item_id, name, args if isinstance(args, dict) else None
            )
        if done:
            result, error = _tool_outcome(item_type, item)
            self.write_tool_result(item_id, result=result, error=error)

    def close(self):
        if self.file is not None:
            self.file.close()


def _tool_outcome(
    item_type: str, item: dict[str, Any]
) -> tuple[str | None, str | None]:
    """The (result, error) text of a finished tool item."""
    status = item.get("status")

    if item_type == "command_execution":
        output = item.get("aggregated_output") or ""
        exit_code = item.get("exit_code")
        if status in ("failed", "declined") or exit_code not in (0, None):
            suffix = f"exit code {exit_code}" if exit_code is not None else str(status)
            return None, f"{output}\n[{suffix}]".strip()
        return output, None

    if item_type == "file_change":
        text = "\n".join(
            f"{c.get('kind', 'change')} {c.get('path', '')}"
            for c in item.get("changes", [])
            if isinstance(c, dict)
        )
        if status == "failed":
            return None, text or "failed"
        return text, None

    if item_type == "mcp_tool_call":
        error = item.get("error")
        if isinstance(error, dict) or status == "failed":
            message = error.get("message") if isinstance(error, dict) else None
            return None, str(message or "failed")
        result = item.get("result")
        if isinstance(result, dict):
            blocks = result.get("content")
            if isinstance(blocks, list):
                texts = [
                    b["text"]
                    for b in blocks
                    if isinstance(b, dict) and isinstance(b.get("text"), str)
                ]
                if texts:
                    return "\n".join(texts), None
            return json.dumps(result), None
        return None, None

    if item_type == "todo_list":
        lines = [
            f"[{'x' if i.get('completed') else ' '}] {i.get('text', '')}"
            for i in item.get("items", [])
            if isinstance(i, dict)
        ]
        return "\n".join(lines), None

    return None, None
