import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from httpx_sse import aconnect_sse
from sse import project
from sse.prompt import TASK_PROMPT

# =============================================================================
# Dialog Writer - Writes dialog.jsonl for SSEBench WebUI consumption
# =============================================================================


class DialogWriter:
    """
    Writes agent dialog entries to $SSE_ARCHIVE/dialog.jsonl.

    Converts OpenCode session events to the SSEBench dialog protocol:
    - init: Session start metadata
    - prompt: User task given to agent
    - message: Assistant text responses
    - thinking: Reasoning blocks
    - tool: Tool calls with status (running/success/error)
    - complete: Session end with stats
    """

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
        return datetime.now(UTC).isoformat()

    def init(self, task: str, cwd: str, model: str, agent: str):
        self._write(
            {
                "seq": self._next_seq(),
                "ts": self._now(),
                "type": "init",
                "data": {"task": task, "cwd": cwd, "model": model, "agent": agent},
            }
        )

    def prompt(self, content: str):
        self._write(
            {
                "seq": self._next_seq(),
                "ts": self._now(),
                "type": "prompt",
                "content": content,
            }
        )

    def message(self, content: str, input_tokens: int = 0, output_tokens: int = 0):
        entry: dict[str, Any] = {
            "seq": self._next_seq(),
            "ts": self._now(),
            "type": "message",
            "role": "assistant",
            "content": content,
        }
        if input_tokens or output_tokens:
            entry["tokens"] = {"in": input_tokens, "out": output_tokens}
        self._write(entry)

    def thinking(self, content: str):
        self._write(
            {
                "seq": self._next_seq(),
                "ts": self._now(),
                "type": "thinking",
                "content": content,
            }
        )

    def tool_start(self, tool_id: str, name: str, args: dict[str, Any] | None = None):
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
        self._write(entry)
        self.pending_tools[tool_id] = name

    def tool_result(
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
        self._write(entry)

    def complete(self, status: str = "success", message: str | None = None):
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
        self._write(entry)

    def close(self):
        self.file.close()


# =============================================================================
# OpenCode Server Management & Client
# =============================================================================

AGENT_PORT = 4097
AGENT_URL = f"http://localhost:{AGENT_PORT}"


def build_opencode_config(
    base_url: str, model_name: str, api_key: str
) -> dict[str, Any]:
    """
    Build a complete OpenCode config for the agent's private server.

    This config is passed via OPENCODE_CONFIG_CONTENT so the server starts
    fully configured — no runtime PATCH /config or PUT /auth calls needed.
    """
    return {
        "provider": {
            "ssebench": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "SSEBench LiteLLM",
                "options": {
                    "baseURL": base_url.rstrip("/") + "/v1",
                    "apiKey": api_key,
                },
                "models": {
                    model_name: {
                        "name": model_name,
                    }
                },
            }
        },
        "model": f"ssebench/{model_name}",
        "mcp": {
            "ssebench": {
                "type": "remote",
                "url": "http://localhost:3000/mcp",
            }
        },
    }


async def start_opencode_server(
    cwd: str, config: dict[str, Any]
) -> asyncio.subprocess.Process:
    """
    Start the agent's own OpenCode server on AGENT_PORT.

    The full config (provider, model, auth, MCP) is passed via the
    OPENCODE_CONFIG_CONTENT env var so the server is ready to use
    immediately after startup. This keeps the agent isolated from
    the entrypoint's WebUI server on port 4096.
    """
    env = {**os.environ, "OPENCODE_CONFIG_CONTENT": json.dumps(config)}
    proc = await asyncio.create_subprocess_exec(
        "opencode",
        "serve",
        "--port",
        str(AGENT_PORT),
        "--hostname",
        "127.0.0.1",
        cwd=cwd,
        env=env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    print(f"[opencode] Agent server started (PID {proc.pid}) on port {AGENT_PORT}")
    return proc


class OpenCodeClient:
    """
    Async HTTP client for the agent's private OpenCode server.

    The agent starts its own OpenCode server (via start_opencode_server)
    that is pre-configured with the LiteLLM provider, model, auth, and
    MCP. This client only needs to create sessions, send prompts, handle
    permissions, and subscribe to SSE events.

    All requests include the x-opencode-directory header, which tells
    OpenCode where the project source code lives.
    """

    def __init__(self, directory: str):
        self.directory = directory
        self.client = httpx.AsyncClient(
            base_url=AGENT_URL,
            headers={"x-opencode-directory": directory},
            timeout=httpx.Timeout(600.0, connect=30.0),
        )

    async def wait_ready(self, timeout: int = 120) -> bool:
        """Poll GET /session until the OpenCode server is responsive."""
        print(f"[opencode] Waiting for server at {AGENT_URL} (timeout: {timeout}s)...")
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = await self.client.get("/session")
                if resp.status_code < 500:
                    elapsed = int(time.time() - start)
                    print(f"[opencode] Server ready after {elapsed}s")
                    return True
            except (httpx.ConnectError, httpx.ReadError, httpx.ConnectTimeout):
                pass
            await asyncio.sleep(1)
        print("[opencode] Server did not become ready in time", file=sys.stderr)
        return False

    async def create_session(self, title: str = "SSEBench") -> str | None:
        """Create a new session. Returns the session ID or None on failure."""
        resp = await self.client.post("/session", json={"title": title})
        if resp.status_code >= 400:
            print(
                f"[opencode] Session creation failed: {resp.status_code}: {resp.text}",
                file=sys.stderr,
            )
            return None
        data = resp.json()
        session_id = data.get("id", "")
        if session_id:
            print(f"[opencode] Session created: {session_id}")
        return session_id or None

    async def send_prompt_async(self, session_id: str, text: str) -> bool:
        """Send a prompt asynchronously (fire-and-forget). Results come via SSE.

        Model selection uses the server's global config (set at startup via
        OPENCODE_CONFIG_CONTENT), not per-prompt overrides.
        """
        body: dict[str, Any] = {
            "parts": [{"type": "text", "text": text}],
        }
        resp = await self.client.post(f"/session/{session_id}/prompt_async", json=body)
        if resp.status_code >= 400:
            print(
                f"[opencode] Prompt send failed: {resp.status_code}: {resp.text}",
                file=sys.stderr,
            )
            return False
        print(f"[opencode] Prompt sent to session {session_id}")
        return True

    async def reply_permission(
        self, session_id: str, permission_id: str, response: str = "always"
    ):
        """Reply to a permission request. Default: always allow."""
        resp = await self.client.post(
            f"/session/{session_id}/permissions/{permission_id}",
            json={"response": response},
        )
        if resp.status_code >= 400:
            print(
                f"[opencode] Permission reply failed: {resp.status_code}",
                file=sys.stderr,
            )

    async def close(self):
        await self.client.aclose()


# =============================================================================
# Event Processor - Maps OpenCode SSE events to dialog entries
# =============================================================================


class EventProcessor:
    """
    Processes OpenCode SSE events and writes dialog entries.

    OpenCode streams events via Server-Sent Events (SSE). Each event has a
    type and properties. This processor maps the relevant event types to
    SSEBench dialog protocol entries:

    - message.part.updated (text)      -> dialog "message"
    - message.part.updated (reasoning) -> dialog "thinking"
    - message.part.updated (tool)      -> dialog "tool" (start/result)
    - message.part.updated (step-finish) -> flush buffered text, track tokens
    - message.updated (assistant)      -> track turns and tokens
    - permission.updated               -> auto-approve
    - session.idle                     -> dialog "complete"
    - session.error                    -> dialog "complete" (error)
    """

    def __init__(self, client: OpenCodeClient, session_id: str, dialog: DialogWriter):
        self.client = client
        self.session_id = session_id
        self.dialog = dialog

        # Text and reasoning parts are streamed in chunks. We buffer
        # the accumulated text per part_id and flush when a non-text
        # event arrives (tool start, step-finish, message complete).
        self.buffered_texts: dict[str, str] = {}
        self.buffered_reasoning: dict[str, str] = {}
        self.flushed_parts: set[str] = set()

        # Tool tracking: avoid writing duplicate start/result entries
        # when the same tool part is updated multiple times.
        self.tool_started: set[str] = set()  # callIDs with start written
        self.tool_completed: set[str] = set()  # callIDs with result written

        # Token tracking per assistant message (avoid double-counting)
        self.counted_messages: set[str] = set()

        # Message role tracking: skip user message parts
        self.user_message_ids: set[str] = set()

        # Completion state
        self.prompt_sent = False
        self.completed = False

    def _flush_buffered(self):
        """Write all buffered text and reasoning parts as dialog entries."""
        for part_id, text in self.buffered_texts.items():
            if part_id not in self.flushed_parts and text.strip():
                self.dialog.message(text)
                self.flushed_parts.add(part_id)
        self.buffered_texts.clear()

        for part_id, text in self.buffered_reasoning.items():
            if part_id not in self.flushed_parts and text.strip():
                self.dialog.thinking(text)
                self.flushed_parts.add(part_id)
        self.buffered_reasoning.clear()

    def _is_our_session(self, event_data: dict[str, Any]) -> bool:
        """Check if event belongs to our session."""
        props = event_data.get("properties", {})
        # sessionID can appear at multiple levels depending on event type
        if props.get("sessionID") == self.session_id:
            return True
        part = props.get("part", {})
        if isinstance(part, dict) and part.get("sessionID") == self.session_id:
            return True
        info = props.get("info", {})
        if isinstance(info, dict) and info.get("sessionID") == self.session_id:
            return True
        return False

    def process_event(self, event_data: dict[str, Any]):
        """Process a single SSE event and emit dialog entries as needed."""
        if not self._is_our_session(event_data):
            return

        event_type = event_data.get("type", "")
        props = event_data.get("properties", {})

        if event_type == "message.part.updated":
            self._handle_part_updated(props)
        elif event_type == "message.updated":
            self._handle_message_updated(props)
        elif event_type == "permission.updated":
            self._handle_permission(props)
        elif event_type in ("session.idle", "session.status"):
            self._handle_session_status(event_type, props)
        elif event_type == "session.error":
            self._handle_session_error(props)

    def _handle_part_updated(self, props: dict[str, Any]):
        """Handle message.part.updated events (assistant parts only)."""
        part = props.get("part", {})
        part_type = part.get("type", "")
        part_id = part.get("id", "")

        # Skip parts belonging to user messages
        message_id = part.get("messageID", "")
        if message_id in self.user_message_ids:
            return

        if part_type == "text":
            # Buffer the full accumulated text (not the delta).
            # We flush when a non-text event arrives.
            text = part.get("text", "")
            if text:
                self.buffered_texts[part_id] = text

        elif part_type == "reasoning":
            text = part.get("text", "")
            if text:
                self.buffered_reasoning[part_id] = text

        elif part_type == "tool":
            call_id = part.get("callID", "")
            tool_name = part.get("tool", "unknown")
            state = part.get("state", {})
            status = state.get("status", "")

            if status == "running" and call_id not in self.tool_started:
                # Flush buffered text before writing tool start
                self._flush_buffered()
                tool_input = state.get("input")
                self.dialog.tool_start(
                    call_id, tool_name, tool_input if tool_input else None
                )
                self.tool_started.add(call_id)

            elif status == "completed" and call_id not in self.tool_completed:
                output = state.get("output", "")
                self.dialog.tool_result(call_id, result=output if output else None)
                self.tool_completed.add(call_id)

            elif status == "error" and call_id not in self.tool_completed:
                error = state.get("error", "Unknown error")
                self.dialog.tool_result(call_id, error=error)
                self.tool_completed.add(call_id)

        elif part_type == "step-finish":
            # Step boundary — flush text and track per-step tokens
            self._flush_buffered()
            tokens = part.get("tokens", {})
            if tokens:
                self.dialog.total_input_tokens += tokens.get("input", 0)
                self.dialog.total_output_tokens += tokens.get("output", 0)

    def _handle_message_updated(self, props: dict[str, Any]):
        """Handle message.updated events. Track user messages, count assistant turns."""
        info = props.get("info", {})
        msg_id = info.get("id", "")

        # Track user message IDs so we can skip their parts
        if info.get("role") == "user" and msg_id:
            self.user_message_ids.add(msg_id)
            return

        if info.get("role") != "assistant":
            return
        time_info = info.get("time", {})

        # Only count a turn when the assistant message is completed
        if time_info.get("completed") and msg_id not in self.counted_messages:
            self.dialog.turns += 1
            self.counted_messages.add(msg_id)
            self._flush_buffered()

    def _handle_permission(self, props: dict[str, Any]):
        """Auto-approve permission requests (we're in a sandboxed container)."""
        session_id = props.get("sessionID", "")
        permission_id = props.get("id", "")
        if session_id == self.session_id and permission_id:
            title = props.get("title", "unknown")
            print(f"[opencode] Auto-approving permission: {title}")
            asyncio.create_task(
                self.client.reply_permission(session_id, permission_id, "always")
            )

    def _handle_session_status(self, event_type: str, props: dict[str, Any]):
        """Handle session.idle and session.status events."""
        is_idle = False
        if event_type == "session.idle":
            is_idle = True
        elif event_type == "session.status":
            status = props.get("status", {})
            if isinstance(status, dict) and status.get("type") == "idle":
                is_idle = True

        # Only complete if the prompt has been sent (avoid the initial idle state)
        if is_idle and self.prompt_sent and not self.completed:
            self._flush_buffered()
            self.completed = True
            self.dialog.complete("success")
            print("[opencode] Session completed successfully")

    def _handle_session_error(self, props: dict[str, Any]):
        """Handle session.error events."""
        if self.completed:
            return
        self._flush_buffered()
        self.completed = True

        error = props.get("error", {})
        if isinstance(error, dict):
            data = error.get("data", {})
            error_msg = (
                data.get("message", "") if isinstance(data, dict) else str(error)
            )
        elif isinstance(error, str):
            error_msg = error
        else:
            error_msg = "Unknown error"

        self.dialog.complete("error", message=error_msg or "Unknown error")
        print(f"[opencode] Session error: {error_msg}", file=sys.stderr)


# =============================================================================
# Main
# =============================================================================


async def run_opencode(dialog: DialogWriter):
    """Main agent execution flow.

    1. Build config and start the agent's own OpenCode server
    2. Wait for the server to be ready
    3. Create a session, subscribe to SSE events, send the task prompt
    4. Process events until completion, then clean up
    """
    try:
        model_name = os.environ["SSE_MODEL_NAME"]
        base_url = os.environ["SSE_BASE_URL"]
        api_key = os.environ["SSE_API_KEY"]
    except KeyError as e:
        dialog.complete("error", message=f"Missing environment variable: {e}")
        return

    cwd = str(project.source)

    # Write dialog init and prompt
    dialog.init(
        task=project.metadata.id,
        cwd=cwd,
        model=model_name,
        agent="opencode",
    )
    dialog.prompt(TASK_PROMPT.strip())

    # Build config and start the agent's own OpenCode server
    config = build_opencode_config(base_url, model_name, api_key)
    server_proc = await start_opencode_server(cwd, config)
    oc = OpenCodeClient(directory=cwd)

    try:
        # Wait for the agent's server to become ready
        if not await oc.wait_ready(timeout=120):
            dialog.complete("error", message="Agent's OpenCode server did not start")
            return

        # Create session (provider, auth, MCP already configured at startup)
        session_id = await oc.create_session(title=f"SSEBench: {project.metadata.id}")
        if not session_id:
            dialog.complete("error", message="Failed to create OpenCode session")
            return

        # Set up event processor
        processor = EventProcessor(oc, session_id, dialog)

        # Subscribe to SSE events in a background task
        async def stream_events():
            """Connect to the SSE event stream and process events.

            Handles transient SSE disconnects gracefully — the OpenCode
            server may close the connection when the container is shutting
            down or after long idle periods.
            """
            try:
                async with httpx.AsyncClient(
                    base_url=AGENT_URL,
                    headers={"x-opencode-directory": cwd},
                    timeout=httpx.Timeout(None),  # No timeout for streaming
                ) as stream_client:
                    async with aconnect_sse(
                        stream_client, "GET", "/event"
                    ) as event_source:
                        async for sse_event in event_source.aiter_sse():
                            if processor.completed:
                                break
                            try:
                                data = json.loads(sse_event.data)
                                processor.process_event(data)
                            except json.JSONDecodeError:
                                pass
            except (httpx.RemoteProtocolError, httpx.ReadError) as e:
                # SSE stream closed by server (container shutdown, etc.)
                if not processor.completed:
                    processor._flush_buffered()
                    print(f"[opencode] SSE stream closed: {e}")

        event_task = asyncio.create_task(stream_events())

        # Brief delay to ensure the event stream is connected before sending
        await asyncio.sleep(1)

        # Send the task prompt (model is set in server's global config)
        success = await oc.send_prompt_async(session_id, TASK_PROMPT.strip())
        if not success:
            event_task.cancel()
            dialog.complete("error", message="Failed to send prompt to OpenCode")
            return

        # Mark that the prompt has been sent so the processor knows
        # that the next session.idle means completion (not the initial state)
        processor.prompt_sent = True

        # Wait for the event stream to finish (processor sets completed=True)
        agent_timeout = int(os.environ.get("TIMEOUT", "3600"))
        try:
            await asyncio.wait_for(event_task, timeout=agent_timeout)
        except TimeoutError:
            if not processor.completed:
                processor._flush_buffered()
                dialog.complete("timeout", message="Agent execution timed out")
                print("[opencode] Agent timed out", file=sys.stderr)
        except asyncio.CancelledError:
            pass

        # If the stream ended without a proper completion event, write one
        if not processor.completed:
            processor._flush_buffered()
            if processor.dialog.turns > 0:
                dialog.complete("success")
                print("[opencode] Session completed (stream ended)")
            else:
                dialog.complete("error", message="SSE stream ended without activity")
                print("[opencode] Stream ended before any turns", file=sys.stderr)

    finally:
        await oc.close()
        # Shut down the agent's OpenCode server
        if server_proc.returncode is None:
            server_proc.terminate()
            try:
                await asyncio.wait_for(server_proc.wait(), timeout=5)
            except TimeoutError:
                server_proc.kill()
            print("[opencode] Agent server stopped")


async def main():
    """Entry point: initialize dialog writer, run the agent, handle errors."""
    dialog = DialogWriter()
    try:
        await run_opencode(dialog)
    except Exception as e:
        print(f"[opencode] Fatal error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        dialog.complete("error", message=str(e))
    finally:
        dialog.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("killed")
