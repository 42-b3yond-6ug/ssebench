import asyncio
import json
import os
import subprocess
import sys
import time
from asyncio.streams import StreamReader
from datetime import UTC, datetime
from io import TextIOWrapper
from pathlib import Path
from typing import Any

from sse import project
from sse.prompt import task_prompt

# =============================================================================
# Dialog Writer - Converts Claude Code stream-json to SSEBench dialog format
# =============================================================================


class DialogWriter:
    """
    Writes agent dialog entries to $SSE_ARCHIVE/dialog.jsonl for WebUI consumption.

    Converts Claude Code's stream-json output to our simplified dialog format:
    - init: Session start metadata
    - prompt: User task given to agent
    - message: Assistant text responses
    - thinking: Reasoning blocks (extended thinking)
    - tool: Tool calls with status (running/success/error)
    - complete: Session end with stats
    """

    def __init__(self, log_path: str | None = None):
        # Default to $SSE_ARCHIVE/dialog.jsonl (archive is shared and world-writable)
        if log_path is None:
            archive = os.environ.get("SSE_ARCHIVE", "/tmp/sse-archive")
            log_path = f"{archive}/dialog.jsonl"
        self.log_path: Path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.seq: int = 0
        self.start_time: float = time.time()
        self.turns: int = 0
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.pending_tools: dict[str, dict[str, str]] = {}  # tool_id -> entry data
        self.completed: bool = False
        self.file: TextIOWrapper = open(self.log_path, "w")

    def _write_entry(self, entry: dict[str, Any]):
        """Write a single entry to the JSONL file."""
        _ = self.file.write(json.dumps(entry) + "\n")
        self.file.flush()

    def _now(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now(UTC).isoformat()

    def _next_seq(self) -> int:
        """Get next sequence number."""
        seq = self.seq
        self.seq += 1
        return seq

    def write_init(self, task: str, cwd: str, model: str, agent: str = "claude-code"):
        """Write session init entry."""
        self._write_entry(
            {
                "seq": self._next_seq(),
                "ts": self._now(),
                "type": "init",
                "data": {
                    "task": task,
                    "cwd": cwd,
                    "model": model,
                    "agent": agent,
                },
            }
        )

    def write_prompt(self, content: str):
        """Write user prompt entry."""
        self._write_entry(
            {
                "seq": self._next_seq(),
                "ts": self._now(),
                "type": "prompt",
                "content": content,
            }
        )

    def write_message(
        self, content: str, input_tokens: int = 0, output_tokens: int = 0
    ):
        """Write assistant message entry."""
        entry: dict[str, Any] = {
            "seq": self._next_seq(),
            "ts": self._now(),
            "type": "message",
            "role": "assistant",
            "content": content,
        }
        if input_tokens > 0 or output_tokens > 0:
            entry["tokens"] = {"in": input_tokens, "out": output_tokens}
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
        self._write_entry(entry)

    def write_thinking(self, content: str):
        """Write thinking/reasoning entry."""
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
        """Write tool call start entry (status=running)."""
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
        self.pending_tools[tool_id] = {"name": name}

    def write_tool_result(
        self, tool_id: str, result: str | None = None, error: str | None = None
    ):
        """Write tool call result entry (status=success or error)."""
        name = self.pending_tools.pop(tool_id, {}).get("name", "unknown")
        entry = {
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
        """Write session completion entry. Guarded against double-writes."""
        if self.completed:
            return
        self.completed = True
        duration_ms = int((time.time() - self.start_time) * 1000)
        entry = {
            "seq": self._next_seq(),
            "ts": self._now(),
            "type": "complete",
            "status": status,
            "turns": self.turns,
            "duration_ms": duration_ms,
            "total_tokens": {
                "in": self.total_input_tokens,
                "out": self.total_output_tokens,
            },
        }
        if message:
            entry["message"] = message
        self._write_entry(entry)

    def process_claude_event(self, event: dict[str, Any]):
        """
        Process a single Claude Code stream-json event and convert to dialog format.

        Claude Code stream-json events include:
        - {"type": "assistant", "message": {...}}
        - {"type": "user", "message": {...}}
        - {"type": "result", ...}
        - {"type": "system", ...}
        """
        event_type = event.get("type", "")

        if event_type == "assistant":
            self.turns += 1
            message = event.get("message", {})
            content_blocks = message.get("content", [])

            # Extract per-turn token usage
            usage = message.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            tokens_attributed = False

            for block in content_blocks:
                block_type = block.get("type", "")

                if block_type == "text":
                    text = block.get("text", "")
                    if text:
                        if not tokens_attributed:
                            self.write_message(text, input_tokens, output_tokens)
                            tokens_attributed = True
                        else:
                            self.write_message(text)

                elif block_type == "thinking":
                    thinking = block.get("thinking", "")
                    if thinking:
                        self.write_thinking(thinking)

                elif block_type == "tool_use":
                    tool_id = block.get("id", str(self._next_seq()))
                    tool_name = block.get("name", "unknown")
                    tool_input = block.get("input", {})
                    self.write_tool_start(tool_id, tool_name, tool_input)

            # If no message was written, still track token usage globally
            if not tokens_attributed:
                self.total_input_tokens += input_tokens
                self.total_output_tokens += output_tokens

        elif event_type == "user":
            message = event.get("message", {})
            content_blocks = message.get("content", [])

            for block in content_blocks:
                block_type = block.get("type", "")

                if block_type == "tool_result":
                    tool_id = block.get("tool_use_id", "")
                    is_error = block.get("is_error", False)
                    content = block.get("content", "")

                    # Content can be string or list of content blocks
                    if isinstance(content, list):
                        text_parts = []
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "text":
                                text_parts.append(c.get("text", ""))
                            elif isinstance(c, str):
                                text_parts.append(c)
                        content = "\n".join(text_parts)

                    if is_error:
                        self.write_tool_result(tool_id, error=content)
                    else:
                        self.write_tool_result(tool_id, result=content)

        elif event_type == "result":
            # Session ended. `result` holds the final text; `subtype` says how it ended.
            subtype = event.get("subtype", "")
            if subtype == "success" and not event.get("is_error", False):
                self.write_complete("success")
            else:
                self.write_complete(
                    "error", message=f"Session ended: {subtype or 'unknown'}"
                )

    def close(self):
        """Close the log file."""
        self.file.close()


# =============================================================================
# Process Output Handling
# =============================================================================


async def stream_output_with_dialog(
    stream: StreamReader, prefix: str = "", dialog: DialogWriter | None = None
):
    """
    Reads from a stream line-by-line, prints it with a prefix,
    and processes JSONL events for dialog logging.
    """
    buf = b""

    while True:
        try:
            chunk = await stream.read(4096)
            buf += chunk
            line_sep = b"\n"
            while line_sep in buf:
                first_line, buf = buf.split(line_sep, maxsplit=1)
                line_str = first_line.decode().strip()
                print(f"{prefix} {line_str}", flush=True)

                # Try to parse as JSON for dialog processing
                if dialog and prefix == "[STDOUT]" and line_str:
                    try:
                        event: dict[str, Any] = json.loads(line_str)
                        dialog.process_claude_event(event)
                    except json.JSONDecodeError:
                        pass  # Not JSON, skip

            if len(chunk) == 0:
                # EOF, prints whatever we have in buf
                remaining = buf.decode().strip()
                if remaining:
                    print(f"{prefix} {remaining}", flush=True)
                break

        except Exception as e:
            print(f"Error reading stream {prefix}: {e}", file=sys.stderr)
            continue


async def run_claude(dialog: DialogWriter):
    try:
        claude_executable = os.environ["CLAUDE"]
        model_name = os.environ["SSE_MODEL_NAME"]
        base_url = os.environ["SSE_BASE_URL"]
        api_key = os.environ["SSE_API_KEY"]
    except KeyError as _:
        dialog.write_complete("error", message="Missing environment variables")
        return

    # Write init entry
    dialog.write_init(
        task=project.metadata.id,
        cwd=str(project.source),
        model=model_name,
        agent="claude-code",
    )

    prompt = task_prompt()
    dialog.write_prompt(prompt)

    # Build Claude command arguments
    # --dangerously-skip-permissions requires non-root user (handled by entrypoint)
    command_args = [
        claude_executable,
        "--verbose",
        "--max-turns",
        "500",
        "-p",
        "--model",
        model_name,
        "--output-format",
        "stream-json",
        "--dangerously-skip-permissions",
        # Passed here rather than written to the project's .claude/, which
        # would become part of the agent's patch.
        "--settings",
        json.dumps({"permissions": {"defaultMode": "bypassPermissions"}}),
    ]

    # Set up environment for Claude Code
    env = os.environ.copy()
    env["ANTHROPIC_BASE_URL"] = base_url
    env["ANTHROPIC_AUTH_TOKEN"] = api_key
    env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] = model_name  # redirects the haiku slot
    env["ANTHROPIC_DEFAULT_SONNET_MODEL"] = model_name  # redirects the sonnet slot
    env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = model_name  # redirects the opus slot

    process = await asyncio.create_subprocess_exec(
        *command_args,
        cwd=project.source,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
        env=env,
    )

    if process.stdin:
        process.stdin.write(prompt.encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()

    assert process.stdout is not None
    assert process.stderr is not None

    stdout_task = asyncio.create_task(
        stream_output_with_dialog(process.stdout, prefix="[STDOUT]", dialog=dialog)
    )
    stderr_task = asyncio.create_task(
        stream_output_with_dialog(process.stderr, prefix="[STDERR]", dialog=None)
    )

    return_code = await process.wait()
    _ = await asyncio.gather(stdout_task, stderr_task)

    # Write completion if not already written by a result event
    if not dialog.completed:
        if return_code == 0:
            dialog.write_complete("success")
        else:
            dialog.write_complete(
                "error", message=f"Process exited with code {return_code}"
            )

    print(f"[claude] exited with code {return_code}")


async def main():
    """
    Main function that configures and launches the Claude Code agent.
    Assumes MCP server is already running on http://localhost:3000/mcp
    """
    claude_executable = os.environ["CLAUDE"]

    # Register the MCP server with Claude Code
    _ = subprocess.run(
        [
            claude_executable,
            "mcp",
            "add",
            "ssebench",
            "http://localhost:3000/mcp",
            "--transport",
            "http",
            "--scope",
            "user",
        ]
    )

    # Initialize dialog writer
    dialog = DialogWriter()

    try:
        # Launch Claude Code agent
        process_task = asyncio.create_task(run_claude(dialog))
        await process_task
    except Exception as e:
        dialog.write_complete("error", message=str(e))
    finally:
        dialog.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("killed")
