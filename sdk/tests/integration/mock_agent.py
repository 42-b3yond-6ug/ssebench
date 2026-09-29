#!/usr/bin/env python3
"""
Mock Claude Code Agent for testing the dialog system.

This simulates Claude Code's behavior by:
1. Writing init entry with session metadata
2. Writing the user prompt
3. Simulating tool calls (read file, edit file, test_patch)
4. Writing assistant messages
5. Writing completion entry

The output is written to /ssebench/log/dialog.jsonl which the SDK daemon
serves via the /agent/dialog endpoint.
"""

import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class DialogWriter:
    """
    Writes agent dialog entries to /ssebench/log/dialog.jsonl for WebUI consumption.
    """

    def __init__(self, log_path: str = "/ssebench/log/dialog.jsonl"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.seq = 0
        self.start_time = time.time()
        self.turns = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.pending_tools: dict[str, dict] = {}
        self.file = open(self.log_path, "w")

    def _write_entry(self, entry: dict):
        """Write a single entry to the JSONL file."""
        self.file.write(json.dumps(entry) + "\n")
        self.file.flush()
        print(f"[dialog] seq={entry['seq']} type={entry['type']}", file=sys.stderr)

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _next_seq(self) -> int:
        seq = self.seq
        self.seq += 1
        return seq

    def write_init(self, task: str, cwd: str, model: str, agent: str = "mock-agent"):
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
        self.turns += 1
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        entry = {
            "seq": self._next_seq(),
            "ts": self._now(),
            "type": "message",
            "role": "assistant",
            "content": content,
        }
        if input_tokens > 0 or output_tokens > 0:
            entry["tokens"] = {"in": input_tokens, "out": output_tokens}
        self._write_entry(entry)

    def write_thinking(self, content: str):
        self._write_entry(
            {
                "seq": self._next_seq(),
                "ts": self._now(),
                "type": "thinking",
                "content": content,
            }
        )

    def write_tool_start(self, tool_id: str, name: str, args: Optional[dict] = None):
        entry = {
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
        self, tool_id: str, result: Optional[str] = None, error: Optional[str] = None
    ):
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

    def write_complete(self, status: str = "success", message: Optional[str] = None):
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

    def close(self):
        self.file.close()


async def simulate_agent(dialog: DialogWriter, fast: bool = False):
    """
    Simulate a Claude Code agent session with realistic delays.

    Args:
        dialog: DialogWriter instance
        fast: If True, use minimal delays (for automated testing)
    """

    def delay(seconds: float):
        if fast:
            return asyncio.sleep(0.1)
        return asyncio.sleep(seconds)

    # Session init
    dialog.write_init(
        task="integration-test-001",
        cwd="/src/buggy",
        model="mock-claude-3.5-sonnet",
        agent="mock-agent",
    )
    await delay(0.5)

    # User prompt
    dialog.write_prompt("""You are an AI agent performing a critical computer security task.
We are working with other AI agents to help each other in our task to discover vulnerabilities,
generate proof-of-vulnerabilities, and patch the vulnerable code.

Project is named test-go-project

All relevant code to the project is written in Go.

A vulnerability has been identified in the source code. You are responsible
for patching this vulnerability by editing the source code.

Issue: The parseInput function in buggy.go has a potential buffer overflow
when handling large input strings.""")
    await delay(1.0)

    # Turn 1: Thinking + initial analysis
    dialog.write_thinking("""Let me analyze the vulnerability described in the issue.

The issue mentions a buffer overflow in parseInput function. I need to:
1. Read the buggy.go file to understand the current implementation
2. Identify the vulnerable code pattern
3. Develop a fix that addresses the root cause
4. Test the fix to ensure it works correctly

Let me start by reading the source file.""")
    await delay(0.5)

    dialog.write_message(
        "I'll analyze the vulnerability in the `parseInput` function. Let me first read the source file to understand the current implementation.",
        input_tokens=1500,
        output_tokens=45,
    )
    await delay(0.5)

    # Tool call 1: Read file
    tool_id_1 = "toolu_01"
    dialog.write_tool_start(tool_id_1, "Read", {"file_path": "/src/buggy/buggy.go"})
    await delay(1.5)

    dialog.write_tool_result(
        tool_id_1,
        result="""package main

import (
    "fmt"
    "strings"
)

// parseInput processes user input - VULNERABLE
func parseInput(input string) string {
    buffer := make([]byte, 256)
    for i, c := range input {
        buffer[i] = byte(c)  // No bounds check!
    }
    return string(buffer)
}

func main() {
    result := parseInput("test input")
    fmt.Println(result)
}""",
    )
    await delay(0.5)

    # Turn 2: Analysis and plan
    dialog.write_thinking("""I can see the vulnerability now. The parseInput function:
1. Creates a fixed-size buffer of 256 bytes
2. Iterates over input string without checking bounds
3. If input is longer than 256 chars, it will cause a buffer overflow

The fix should:
1. Check the input length before copying
2. Either truncate or return an error for oversized input
3. Or use append() which handles dynamic sizing

I'll go with the bounds checking approach as it's most explicit.""")
    await delay(0.5)

    dialog.write_message(
        """I've identified the vulnerability. The `parseInput` function creates a fixed 256-byte buffer but doesn't check if the input string exceeds this limit. This can cause a buffer overflow (index out of bounds panic in Go).

I'll fix this by adding a bounds check before copying. Let me edit the file.""",
        input_tokens=800,
        output_tokens=75,
    )
    await delay(0.5)

    # Tool call 2: Edit file
    tool_id_2 = "toolu_02"
    dialog.write_tool_start(
        tool_id_2,
        "Edit",
        {
            "file_path": "/src/buggy/buggy.go",
            "old_string": "func parseInput(input string) string {\n    buffer := make([]byte, 256)",
            "new_string": "func parseInput(input string) string {\n    const maxLen = 256\n    if len(input) > maxLen {\n        input = input[:maxLen]\n    }\n    buffer := make([]byte, maxLen)",
        },
    )
    await delay(2.0)

    dialog.write_tool_result(
        tool_id_2, result="Successfully edited /src/buggy/buggy.go"
    )
    await delay(0.5)

    # Turn 3: Test the patch
    dialog.write_message(
        "I've added a bounds check that truncates input strings longer than 256 characters. Now let me test the patch to ensure it compiles and passes all tests.",
        input_tokens=600,
        output_tokens=40,
    )
    await delay(0.5)

    # Tool call 3: Test patch
    tool_id_3 = "toolu_03"
    dialog.write_tool_start(tool_id_3, "test_patch", {})
    await delay(3.0)

    dialog.write_tool_result(
        tool_id_3,
        result="""Build: SUCCESS
PoC Test: PASS (no crash with large input)
Functionality Test: PASS (3/3 tests passed)

All checks passed!""",
    )
    await delay(0.5)

    # Turn 4: Completion
    dialog.write_message(
        """The patch has been successfully applied and all tests pass:

1. **Build**: The project compiles without errors
2. **PoC Test**: The proof-of-vulnerability no longer causes a crash
3. **Functionality Tests**: All 3 tests pass, confirming normal behavior is preserved

The fix adds a simple bounds check that truncates oversized input strings, preventing the buffer overflow while maintaining the expected functionality for normal-sized inputs.""",
        input_tokens=500,
        output_tokens=95,
    )
    await delay(0.5)

    # Session complete
    dialog.write_complete("success", message="Patch successfully applied and verified")


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Mock Claude Code agent for dialog testing"
    )
    parser.add_argument(
        "--fast", action="store_true", help="Use minimal delays for automated testing"
    )
    parser.add_argument(
        "--loop", action="store_true", help="Run continuously (for interactive testing)"
    )
    args = parser.parse_args()

    print("[mock-agent] Starting mock Claude Code agent...", file=sys.stderr)

    if args.loop:
        # Loop mode: restart simulation every 30 seconds
        while True:
            dialog = DialogWriter()
            try:
                await simulate_agent(dialog, fast=args.fast)
                dialog.close()
                print(
                    "[mock-agent] Session complete. Restarting in 30 seconds...",
                    file=sys.stderr,
                )
                await asyncio.sleep(30)
            except Exception as e:
                print(f"[mock-agent] Error: {e}", file=sys.stderr)
                dialog.write_complete("error", message=str(e))
                dialog.close()
                await asyncio.sleep(5)
    else:
        # Single run mode
        dialog = DialogWriter()
        try:
            await simulate_agent(dialog, fast=args.fast)
        except Exception as e:
            print(f"[mock-agent] Error: {e}", file=sys.stderr)
            dialog.write_complete("error", message=str(e))
        finally:
            dialog.close()

    print("[mock-agent] Done.", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
