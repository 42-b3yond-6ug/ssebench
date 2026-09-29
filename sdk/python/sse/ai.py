"""OpenCode agent wrapper.

Provides a reusable async client for starting an OpenCode server,
creating sessions, sending prompts, and collecting responses.

Usage::

    from sse.ai import OpenCodeAgent, build_opencode_config

    config = build_opencode_config("claude-sonnet-4-20250514")
    async with OpenCodeAgent(directory="/path/to/project", config=config) as agent:
        session_id = await agent.create_session()
        response = await agent.send_prompt(session_id, "hello")
        print(response.final_message)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Literal, Required

import httpx
from typing_extensions import TypedDict

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# API type definitions (matching OpenCode OpenAPI 3.1 spec)
# ---------------------------------------------------------------------------

# -- Request types --


class _TextPartInput(TypedDict):
    """A text part in a message request body."""

    type: Literal["text"]
    text: str


class _SendMessageBody(TypedDict, total=False):
    """Request body for ``POST /session/:id/message``."""

    parts: Required[list[_TextPartInput]]
    messageID: str
    agent: str
    noReply: bool
    system: str
    tools: dict[str, bool]


class _CreateSessionBody(TypedDict, total=False):
    """Request body for ``POST /session``."""

    title: str
    parentID: str


# -- Response types --


class _SessionResponse(TypedDict):
    """Subset of the ``Session`` schema returned by ``POST /session``."""

    id: str
    title: str


class _PartResponse(TypedDict, total=False):
    """Union of all ``Part`` variants.

    Only the common fields and the ``text`` field (for ``TextPart``) are
    typed here; other variant-specific fields are accessed via ``dict``
    when needed.
    """

    id: Required[str]
    sessionID: Required[str]
    messageID: Required[str]
    type: Required[str]  # discriminator: "text", "tool", "reasoning", ...
    text: str  # present only when type == "text"


class _TokenCache(TypedDict):
    """Cache token counts inside ``_TokenUsage``."""

    read: int
    write: int


class _TokenUsage(TypedDict, total=False):
    """Token usage reported in an ``AssistantMessage``."""

    input: Required[int]
    output: Required[int]
    reasoning: Required[int]
    cache: Required[_TokenCache]
    total: int


class _AssistantMessageResponse(TypedDict, total=False):
    """Subset of the ``AssistantMessage`` schema we inspect."""

    id: Required[str]
    sessionID: Required[str]
    role: Required[Literal["assistant"]]
    cost: Required[float]
    tokens: Required[_TokenUsage]
    modelID: str
    providerID: str


class _SyncMessageResponse(TypedDict):
    """Response from ``POST /session/:id/message`` (synchronous)."""

    info: _AssistantMessageResponse
    parts: list[_PartResponse]


class _MessageEntry(TypedDict):
    """One element returned by ``GET /session/:id/message``.

    The ``info`` field can be either a ``UserMessage`` or an
    ``AssistantMessage``; we only inspect the ``role`` field here.
    """

    info: dict[str, Any]
    parts: list[_PartResponse]


# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentResponse:
    """Structured response from an OpenCode agent session."""

    final_message: str
    """Text parts from the last assistant message only."""
    full_log: str
    """All text parts from every message in the session."""


# ---------------------------------------------------------------------------
# Configuration helper
# ---------------------------------------------------------------------------


def build_opencode_config(
    model_name: str | None = None,
    mcp_url: str | None = None,
) -> dict[str, Any]:
    """Build a complete OpenCode config.

    When ``SSE_MODEL_NAME``, ``SSE_BASE_URL`` and ``SSE_API_KEY`` are set, as they are in a task
    container, the config uses the run's model through the LiteLLM proxy and ignores
    ``model_name``. Otherwise it uses ``model_name`` with OpenCode's built-in Anthropic provider,
    which reads the ``ANTHROPIC_API_KEY`` environment variable at runtime -- the key is **not**
    embedded in the config dict.

    Args:
        model_name: Anthropic model identifier (e.g. ``claude-sonnet-4-20250514``); required
            when the ``SSE_*`` variables are not all set.
        mcp_url: Optional MCP server URL to register.

    Returns:
        Config dict suitable for the ``OPENCODE_CONFIG_CONTENT`` env var.

    Raises:
        ValueError: If ``model_name`` is missing and the ``SSE_*`` variables are not all set.
    """
    config: dict[str, Any] = {}

    sse_model_name = os.environ.get("SSE_MODEL_NAME")
    sse_base_url = os.environ.get("SSE_BASE_URL")
    sse_api_key = os.environ.get("SSE_API_KEY")

    if sse_model_name and sse_base_url and sse_api_key:
        config["provider"] = {
            "ssebench": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "SSEBench built-in provider",
                "options": {
                    "baseURL": sse_base_url,
                    "apiKey": sse_api_key,
                },
                "models": {sse_model_name: {"name": "SSEBench built-in model"}},
            }
        }
        config["model"] = f"ssebench/{sse_model_name}"
    else:
        if model_name is None:
            raise ValueError(
                "model_name is required when SSE_MODEL_NAME, SSE_BASE_URL, "
                "and SSE_API_KEY environment variables are not all set"
            )
        config["model"] = f"anthropic/{model_name}"

    if mcp_url:
        config["mcp"] = {
            "ssebench": {
                "type": "remote",
                "url": mcp_url,
            }
        }

    config["permission"] = "allow"

    return config


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------


def _extract_text(parts: list[_PartResponse]) -> str:
    """Join text content from a list of message parts.

    Only parts with ``type == "text"`` are included; empty/whitespace-only
    parts are skipped.
    """
    return "\n".join(
        text
        for p in parts
        if p["type"] == "text" and (text := p.get("text", "")).strip()
    )


def _extract_all_text(messages: list[_MessageEntry]) -> str:
    """Join all text content across every message in a session."""
    segments: list[str] = []
    for entry in messages:
        text = _extract_text(entry["parts"])
        if text:
            segments.append(text)
    return "\n".join(segments)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class OpenCodeAgent:
    """Async wrapper for the OpenCode agent server.

    Manages the full lifecycle: start the server, create sessions,
    send prompts, collect responses, and shut down cleanly.

    With a config that uses OpenCode's built-in Anthropic provider (see
    :func:`build_opencode_config`), the Anthropic API key must be available as
    the ``ANTHROPIC_API_KEY`` environment variable in the process that runs
    this agent.

    Usage::

        from sse.ai import OpenCodeAgent, build_opencode_config

        config = build_opencode_config("claude-sonnet-4-20250514")
        async with OpenCodeAgent(directory="/path/to/project", config=config) as agent:
            session_id = await agent.create_session()
            response = await agent.send_prompt(session_id, "hello")
            print(response)
    """

    def __init__(
        self,
        directory: str,
        config: dict[str, Any],
        port: int = 4097,
        hostname: str = "127.0.0.1",
    ) -> None:
        self.directory = directory
        self.config = config
        self.port = port
        self.hostname = hostname
        self.base_url = f"http://{hostname}:{port}"
        self._process: asyncio.subprocess.Process | None = None
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, timeout: int = 120) -> None:
        """Start the OpenCode server and block until it is ready.

        Args:
            timeout: Maximum seconds to wait for server readiness.

        Raises:
            RuntimeError: If the server process exits prematurely.
            TimeoutError: If the server does not become ready in time.
        """
        env = {**os.environ, "OPENCODE_CONFIG_CONTENT": json.dumps(self.config)}
        self._process = await asyncio.create_subprocess_exec(
            "opencode",
            "serve",
            "--port",
            str(self.port),
            "--hostname",
            self.hostname,
            cwd=self.directory,
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        log.info("Server started (PID %s) on port %s", self._process.pid, self.port)

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"x-opencode-directory": self.directory},
        )

        try:
            start_time = time.monotonic()
            while time.monotonic() - start_time < timeout:
                try:
                    resp = await self._client.get("/session")
                    if resp.status_code < 400:
                        elapsed = int(time.monotonic() - start_time)
                        log.info("Server ready after %ss", elapsed)
                        return
                except (httpx.ConnectError, httpx.ReadError, httpx.ConnectTimeout):
                    pass
                if self._process.returncode is not None:
                    raise RuntimeError(
                        f"OpenCode server exited prematurely "
                        f"with code {self._process.returncode}"
                    )
                await asyncio.sleep(1)

            raise TimeoutError(
                f"OpenCode server did not become ready within {timeout}s"
            )
        except BaseException:
            await self.stop()
            raise

    async def stop(self) -> None:
        """Shut down the OpenCode server and close the HTTP client."""
        try:
            if self._client:
                await self._client.aclose()
        finally:
            self._client = None
            proc = self._process
            self._process = None
            if proc and proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
                log.info("Server stopped")

    async def __aenter__(self) -> OpenCodeAgent:
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.stop()

    # ------------------------------------------------------------------
    # HTTP client accessor
    # ------------------------------------------------------------------

    @property
    def _http(self) -> httpx.AsyncClient:
        """Return the HTTP client, raising if the agent has not been started."""
        if self._client is None:
            raise RuntimeError("Agent not started -- call start() first")
        return self._client

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def create_session(self, title: str = "Session") -> str:
        """Create a new chat session.

        Args:
            title: Human-readable session title.

        Returns:
            The session ID string.

        Raises:
            httpx.HTTPStatusError: If session creation fails.
        """
        body: _CreateSessionBody = {"title": title}
        resp = await self._http.post("/session", json=body)
        resp.raise_for_status()
        session: _SessionResponse = resp.json()
        log.info("Session created: %s", session["id"])
        return session["id"]

    # ------------------------------------------------------------------
    # Prompt and response
    # ------------------------------------------------------------------

    async def send_prompt(
        self,
        session_id: str,
        text: str,
        timeout: float = 300.0,
    ) -> AgentResponse:
        """Send a prompt and wait for the complete response.

        Uses the synchronous ``POST /session/:id/message`` endpoint which
        blocks until the assistant finishes responding.  After receiving the
        response, all session messages are fetched to build the full
        conversation log.

        Args:
            session_id: Target session ID (from :meth:`create_session`).
            text: The prompt text.
            timeout: Maximum seconds to wait for the assistant to finish.
                If exceeded, ``final_message`` will contain a timeout
                indicator and ``full_log`` will contain whatever messages
                were available at that point.

        Returns:
            An :class:`AgentResponse` containing the final assistant
            message text (or a timeout indicator) and the full
            conversation log.

        Raises:
            httpx.HTTPStatusError: On HTTP-level failures from the server.
        """
        body: _SendMessageBody = {"parts": [{"type": "text", "text": text}]}

        timed_out = False
        try:
            resp = await self._http.post(
                f"/session/{session_id}/message",
                json=body,
                timeout=httpx.Timeout(timeout, connect=5.0),
            )
            resp.raise_for_status()
            result: _SyncMessageResponse = resp.json()
            final_message = _extract_text(result["parts"])
        except httpx.TimeoutException:
            timed_out = True
            final_message = f"[timeout] Response not completed within {timeout}s"

        log.info("Prompt sent to session %s", session_id)

        # Always fetch the full conversation log -- partial progress is
        # still valuable when the response timed out.
        all_resp = await self._http.get(
            f"/session/{session_id}/message",
            timeout=httpx.Timeout(30.0, connect=5.0),
        )
        all_resp.raise_for_status()
        messages: list[_MessageEntry] = all_resp.json()
        full_log = _extract_all_text(messages)

        if timed_out:
            log.warning("Timed out after %ss, returning partial log", timeout)

        return AgentResponse(final_message=final_message, full_log=full_log)
