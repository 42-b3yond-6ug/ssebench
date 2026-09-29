"""A stand-in for the LiteLLM proxy that answers every model call with "I'm done."

It speaks the three APIs the bundled agents use: Anthropic Messages (claude-code),
OpenAI Responses (codex) and OpenAI Chat Completions (opencode), streaming or not,
with or without the /v1 prefix. Each request is logged to standard output as one
JSON line, so a test can tell which agent called what.

    python stub_llm.py [PORT]      # default 4000, the proxy's port

Standard library only: it runs in a plain Python image on a network without
internet access.
"""

from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

ANSWER = "I'm done."


def sse(events: list[tuple[str | None, dict[str, Any] | str]]) -> bytes:
    out = []
    for name, data in events:
        if name:
            out.append(f"event: {name}\n")
        out.append(f"data: {data if isinstance(data, str) else json.dumps(data)}\n\n")
    return "".join(out).encode()


def anthropic(model: str, stream: bool) -> tuple[str, bytes]:
    usage = {"input_tokens": 1, "output_tokens": 3}
    if not stream:
        body = {
            "id": "msg_stub",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [{"type": "text", "text": ANSWER}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": usage,
        }
        return "application/json", json.dumps(body).encode()
    message = {
        "id": "msg_stub",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [],
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    return "text/event-stream", sse(
        [
            ("message_start", {"type": "message_start", "message": message}),
            (
                "content_block_start",
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
            ),
            (
                "content_block_delta",
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": ANSWER}},
            ),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            (
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 3},
                },
            ),
            ("message_stop", {"type": "message_stop"}),
        ]
    )


def chat_completions(model: str, stream: bool) -> tuple[str, bytes]:
    usage = {"prompt_tokens": 1, "completion_tokens": 3, "total_tokens": 4}
    if not stream:
        body = {
            "id": "chatcmpl-stub",
            "object": "chat.completion",
            "created": 0,
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": ANSWER}, "finish_reason": "stop"}],
            "usage": usage,
        }
        return "application/json", json.dumps(body).encode()

    def chunk(delta: dict[str, Any], finish: str | None, **extra: Any) -> dict[str, Any]:
        return {
            "id": "chatcmpl-stub",
            "object": "chat.completion.chunk",
            "created": 0,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            **extra,
        }

    return "text/event-stream", sse(
        [
            (None, chunk({"role": "assistant", "content": ANSWER}, None)),
            (None, chunk({}, "stop", usage=usage)),
            (None, "[DONE]"),
        ]
    )


def responses(model: str, stream: bool) -> tuple[str, bytes]:
    item = {
        "type": "message",
        "id": "msg_stub",
        "status": "completed",
        "role": "assistant",
        "content": [{"type": "output_text", "text": ANSWER, "annotations": []}],
    }
    response = {
        "id": "resp_stub",
        "object": "response",
        "created_at": 0,
        "status": "completed",
        "model": model,
        "output": [item],
        "usage": {
            "input_tokens": 1,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens": 3,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 4,
        },
    }
    if not stream:
        return "application/json", json.dumps(response).encode()
    in_progress = {**response, "status": "in_progress", "output": []}
    added = {**item, "status": "in_progress", "content": []}
    part = {"type": "output_text", "text": "", "annotations": []}
    ids = {"item_id": "msg_stub", "output_index": 0, "content_index": 0}
    return "text/event-stream", sse(
        [
            ("response.created", {"type": "response.created", "response": in_progress}),
            ("response.in_progress", {"type": "response.in_progress", "response": in_progress}),
            ("response.output_item.added", {"type": "response.output_item.added", "output_index": 0, "item": added}),
            ("response.content_part.added", {"type": "response.content_part.added", **ids, "part": part}),
            ("response.output_text.delta", {"type": "response.output_text.delta", **ids, "delta": ANSWER}),
            ("response.output_text.done", {"type": "response.output_text.done", **ids, "text": ANSWER}),
            (
                "response.content_part.done",
                {"type": "response.content_part.done", **ids, "part": {**part, "text": ANSWER}},
            ),
            ("response.output_item.done", {"type": "response.output_item.done", "output_index": 0, "item": item}),
            ("response.completed", {"type": "response.completed", "response": response}),
        ]
    )


ROUTES = {
    "/messages": anthropic,
    "/chat/completions": chat_completions,
    "/responses": responses,
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def record(self, **fields: Any) -> None:
        print(json.dumps({"method": self.command, "path": self.path, **fields}), flush=True)

    def reply(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if content_type == "text/event-stream":
            self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def route(self) -> str:
        path = self.path.split("?", 1)[0].rstrip("/")
        return path.removeprefix("/v1")

    def do_GET(self) -> None:
        self.record()
        if self.route() in ("", "/health", "/health/liveliness"):
            self.reply(200, "application/json", b'{"status": "ok"}')
        elif self.route() == "/models":
            body = {"object": "list", "data": [{"id": "stub", "object": "model", "owned_by": "stub"}]}
            self.reply(200, "application/json", json.dumps(body).encode())
        else:
            self.reply(404, "application/json", b'{"error": "not found"}')

    def do_HEAD(self) -> None:
        self.record()
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            request = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            request = {}
        model = str(request.get("model", "stub"))
        stream = bool(request.get("stream"))
        self.record(model=model, stream=stream)
        route = self.route()
        if route == "/messages/count_tokens":
            self.reply(200, "application/json", b'{"input_tokens": 1}')
        elif route in ROUTES:
            self.reply(200, *ROUTES[route](model, stream))
        else:
            self.reply(404, "application/json", b'{"error": "not found"}')


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(json.dumps({"listening": port}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
