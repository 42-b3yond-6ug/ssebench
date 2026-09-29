---
outline: deep
---

# Dialog protocol

This guide explains the **dialog protocol** — a JSONL-based log format that allows the SSEBench WebUI to display any agent's session in a unified way, regardless of the underlying agent implementation.

## Overview

When your agent runs inside an SSEBench container, the WebUI needs a way to show what happened: what the agent thought, which tools it called, and how the session ended. The dialog protocol bridges this gap.

Your agent writes a single file — `dialog.jsonl` — containing one JSON object per line. Each object represents a discrete event in the agent's session (a message, a tool call, a reasoning step, etc.). The WebUI reads this file and renders the session timeline.

**File location:** `$SSE_ARCHIVE/dialog.jsonl`

The `SSE_ARCHIVE` environment variable points to a shared, world-writable directory (defaults to `/tmp/sse-archive` if unset). Write your `dialog.jsonl` there.

## File Format

- **Encoding:** UTF-8
- **Format:** [JSON Lines](https://jsonlines.org/) — one JSON object per line, no trailing commas
- **Write mode:** Overwrite (`"w"`), not append — each agent run produces a fresh file
- **Flushing:** Flush after every entry so the WebUI can stream progress in real time

## Common Fields

Every entry has these three fields:

| Field | Type | Description |
|-------|------|-------------|
| `seq` | `int` | Monotonically increasing sequence number, starting at `0` |
| `ts` | `string` | ISO 8601 timestamp in UTC (e.g. `"2025-01-15T10:30:00.123456+00:00"`) |
| `type` | `string` | Entry type: `init`, `prompt`, `message`, `thinking`, `tool`, or `complete` |

## Entry Types

### `init`

The first entry in every dialog file. Contains session metadata.

| Field | Type | Description |
|-------|------|-------------|
| `data.task` | `string` | Task ID |
| `data.cwd` | `string` | Working directory path |
| `data.model` | `string` | LLM model name |
| `data.agent` | `string` | Agent identifier |

```json
{
  "seq": 0,
  "ts": "2025-01-15T10:30:00+00:00",
  "type": "init",
  "data": {
    "task": "CVE-2023-1234",
    "cwd": "/src/project",
    "model": "claude-opus-4-5",
    "agent": "my-agent"
  }
}
```

### `prompt`

The user prompt (task description) sent to the agent. Typically appears once, immediately after `init`.

| Field | Type | Description |
|-------|------|-------------|
| `content` | `string` | The full prompt text |

```json
{
  "seq": 1,
  "ts": "2025-01-15T10:30:01+00:00",
  "type": "prompt",
  "content": "You are a security engineer. Fix the buffer overflow in src/parser.c..."
}
```

### `message`

A text response from the assistant.

| Field | Type | Description |
|-------|------|-------------|
| `role` | `string` | Always `"assistant"` |
| `content` | `string` | The message text (may contain markdown) |
| `tokens` | `object` | *(Optional)* Token usage: `{"in": <int>, "out": <int>}` |

```json
{
  "seq": 2,
  "ts": "2025-01-15T10:30:05+00:00",
  "type": "message",
  "role": "assistant",
  "content": "I'll start by examining the vulnerable function in src/parser.c.",
  "tokens": {"in": 1500, "out": 42}
}
```

The `tokens` field is optional. Include it when your agent has access to per-turn token counts.

### `thinking`

A reasoning or chain-of-thought block. This is displayed differently from regular messages in the WebUI (typically collapsed or styled as internal reasoning).

| Field | Type | Description |
|-------|------|-------------|
| `content` | `string` | The thinking/reasoning text |

```json
{
  "seq": 3,
  "ts": "2025-01-15T10:30:06+00:00",
  "type": "thinking",
  "content": "The vulnerability is in the parse_header function at line 142. The buffer is allocated with a fixed size of 256 bytes but the input length is not checked..."
}
```

### `tool`

A tool call event. Tool entries come in **pairs**: a **start** entry (`status: "running"`) followed by a **result** entry (`status: "success"` or `"error"`). The two entries are correlated by `tool_id`.

#### Tool Start

| Field | Type | Description |
|-------|------|-------------|
| `tool_id` | `string` | Unique identifier for this tool invocation |
| `name` | `string` | Tool name (e.g. `"bash"`, `"edit"`, `"read"`) |
| `status` | `string` | `"running"` |
| `args` | `object` | *(Optional)* Tool input arguments |

```json
{
  "seq": 4,
  "ts": "2025-01-15T10:30:07+00:00",
  "type": "tool",
  "tool_id": "tool_abc123",
  "name": "bash",
  "status": "running",
  "args": {"command": "gcc -o parser src/parser.c"}
}
```

#### Tool Result

| Field | Type | Description |
|-------|------|-------------|
| `tool_id` | `string` | Same `tool_id` as the corresponding start entry |
| `name` | `string` | Tool name (carried over from start) |
| `status` | `string` | `"success"` or `"error"` |
| `result` | `string` | *(Optional)* Tool output on success |
| `error` | `string` | *(Optional)* Error message on failure |

```json
{
  "seq": 5,
  "ts": "2025-01-15T10:30:10+00:00",
  "type": "tool",
  "tool_id": "tool_abc123",
  "name": "bash",
  "status": "success",
  "result": "Compilation successful"
}
```

Error example:

```json
{
  "seq": 5,
  "ts": "2025-01-15T10:30:10+00:00",
  "type": "tool",
  "tool_id": "tool_abc123",
  "name": "bash",
  "status": "error",
  "error": "src/parser.c:142: error: implicit declaration of function 'strlen'"
}
```

### `complete`

The final entry. Signals that the agent session has ended.

| Field | Type | Description |
|-------|------|-------------|
| `status` | `string` | `"success"`, `"error"`, or `"timeout"` |
| `turns` | `int` | Number of assistant turns |
| `duration_ms` | `int` | Total session duration in milliseconds |
| `total_tokens` | `object` | Aggregate token usage: `{"in": <int>, "out": <int>}` |
| `message` | `string` | *(Optional)* Additional context (e.g. error description) |

```json
{
  "seq": 20,
  "ts": "2025-01-15T10:35:00+00:00",
  "type": "complete",
  "status": "success",
  "turns": 8,
  "duration_ms": 300000,
  "total_tokens": {"in": 45000, "out": 12000}
}
```

## Entry Ordering

A well-formed dialog file follows this order:

```
init → prompt → [message | thinking | tool]* → complete
```

1. **`init`** must be the first entry (`seq: 0`)
2. **`prompt`** should follow immediately after `init`
3. **`message`**, **`thinking`**, and **`tool`** entries are interleaved in the order they occur
4. **`complete`** must be the last entry

Within tool calls, every `tool` start (`status: "running"`) should eventually have a matching `tool` result (`status: "success"` or `"error"`) with the same `tool_id`. Multiple tool calls can be in flight concurrently (interleaved starts before results).

## Reference Implementation

Below is a minimal `DialogWriter` class you can copy into your agent. It handles sequencing, timestamps, tool correlation, and token tracking.

```python
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DialogWriter:
    """Writes dialog.jsonl for SSEBench WebUI consumption."""

    def __init__(self):
        archive = os.environ.get("SSE_ARCHIVE", "/tmp/sse-archive")
        self.log_path = Path(archive) / "dialog.jsonl"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.seq = 0
        self.start_time = time.time()
        self.turns = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.pending_tools: dict[str, str] = {}  # tool_id -> tool name
        self.file = open(self.log_path, "w")

    def _write(self, entry: dict[str, Any]):
        self.file.write(json.dumps(entry) + "\n")
        self.file.flush()

    def _next_seq(self) -> int:
        seq = self.seq
        self.seq += 1
        return seq

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def init(self, task: str, cwd: str, model: str, agent: str):
        self._write({
            "seq": self._next_seq(), "ts": self._now(), "type": "init",
            "data": {"task": task, "cwd": cwd, "model": model, "agent": agent},
        })

    def prompt(self, content: str):
        self._write({
            "seq": self._next_seq(), "ts": self._now(),
            "type": "prompt", "content": content,
        })

    def message(self, content: str, input_tokens: int = 0, output_tokens: int = 0):
        self.turns += 1
        entry: dict[str, Any] = {
            "seq": self._next_seq(), "ts": self._now(),
            "type": "message", "role": "assistant", "content": content,
        }
        if input_tokens or output_tokens:
            entry["tokens"] = {"in": input_tokens, "out": output_tokens}
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
        self._write(entry)

    def thinking(self, content: str):
        self._write({
            "seq": self._next_seq(), "ts": self._now(),
            "type": "thinking", "content": content,
        })

    def tool_start(self, tool_id: str, name: str, args: dict | None = None):
        entry: dict[str, Any] = {
            "seq": self._next_seq(), "ts": self._now(), "type": "tool",
            "tool_id": tool_id, "name": name, "status": "running",
        }
        if args:
            entry["args"] = args
        self._write(entry)
        self.pending_tools[tool_id] = name

    def tool_result(self, tool_id: str, result: str | None = None, error: str | None = None):
        name = self.pending_tools.pop(tool_id, "unknown")
        entry: dict[str, Any] = {
            "seq": self._next_seq(), "ts": self._now(), "type": "tool",
            "tool_id": tool_id, "name": name,
            "status": "error" if error else "success",
        }
        if result:
            entry["result"] = result
        if error:
            entry["error"] = error
        self._write(entry)

    def complete(self, status: str = "success", message: str | None = None):
        entry: dict[str, Any] = {
            "seq": self._next_seq(), "ts": self._now(), "type": "complete",
            "status": status, "turns": self.turns,
            "duration_ms": int((time.time() - self.start_time) * 1000),
            "total_tokens": {"in": self.total_input_tokens, "out": self.total_output_tokens},
        }
        if message:
            entry["message"] = message
        self._write(entry)

    def close(self):
        self.file.close()
```

### Usage Example

```python
import os

dialog = DialogWriter()
try:
    dialog.init(
        task="CVE-2023-1234",
        cwd="/src/project",
        model=os.environ["SSE_MODEL_NAME"],
        agent="my-agent",
    )
    dialog.prompt("Fix the buffer overflow vulnerability...")

    # Your agent loop:
    dialog.thinking("Analyzing the vulnerable function...")
    dialog.message("I found the issue in src/parser.c line 142.")

    dialog.tool_start("call_1", "bash", {"command": "gcc -o parser src/parser.c"})
    dialog.tool_result("call_1", result="Compilation successful")

    dialog.message("The fix has been applied and verified.")
    dialog.complete("success")
except Exception as e:
    dialog.complete("error", message=str(e))
finally:
    dialog.close()
```

## Canonical Implementation

The Claude Code agent wrapper at `agents/claude-code/claude-code-sse/main.py` is the canonical implementation of this protocol. It converts Claude Code's `stream-json` output format into dialog entries in real time. Refer to it for a production-grade example, including async streaming and token tracking.

## Next steps

- [Add an agent](/guides/add-an-agent#report-the-session): write a dialog from a
  minimal agent
- [MCP server](/reference/mcp-server): the `test_patch` tool
- [Environment variables](/reference/environment): every variable available to an agent
