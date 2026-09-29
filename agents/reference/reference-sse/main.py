"""Apply the task's reference patch to the source tree, then exit.

A reference run grades the task's known fix instead of a model's patch, so it
checks the task and the grading pipeline and costs nothing. `ssebench run`
mounts the fix read-only at REFERENCE_PATCH for this agent and no other; the
daemon withholds it during the agent phase like it does for every agent.
"""

from __future__ import annotations

import json
import os
import pwd
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sse import project

REFERENCE_PATCH = Path("/reference/patch.diff")

# git first; patch(1) for fixes that only apply with fuzz, as the dataset
# validator does.
APPLY_COMMANDS = (
    ["git", "apply", "-p1"],
    ["patch", "--batch", "--forward", "--no-backup-if-mismatch", "-p1", "-i"],
)


class Dialog:
    """Writes dialog.jsonl so the web UI shows what the agent did."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("w")
        self.seq = 0
        self.start = time.monotonic()

    def write(self, entry_type: str, **fields: Any) -> None:
        entry = {
            "seq": self.seq,
            "ts": datetime.now(UTC).isoformat(),
            "type": entry_type,
            **fields,
        }
        self.seq += 1
        _ = self.file.write(json.dumps(entry) + "\n")
        self.file.flush()

    def complete(self, status: str, message: str) -> None:
        self.write(
            "complete",
            status=status,
            turns=0,
            duration_ms=int((time.monotonic() - self.start) * 1000),
            total_tokens={"in": 0, "out": 0},
            message=message,
        )
        self.file.close()


def run(cmd: list[str], cwd: Path, env: dict[str, str]) -> tuple[bool, str]:
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()


def apply_patch(patch: Path, source: Path, env: dict[str, str]) -> tuple[bool, str]:
    """Apply the patch to the working tree and stage it.

    The grader diffs the index and the working tree against HEAD, so files the
    patch adds must be staged to count.
    """
    errors: list[str] = []
    for cmd in APPLY_COMMANDS:
        ok, output = run([*cmd, str(patch)], source, env)
        if ok:
            ok, output = run(["git", "add", "--all"], source, env)
            if not ok:
                return False, f"git add failed: {output}"
            _, stat = run(["git", "diff", "--cached", "--stat"], source, env)
            return True, f"Applied with {cmd[0]}:\n{stat}"
        errors.append(f"{' '.join(cmd)}: {output}")
    return False, "\n".join(errors)


def main() -> int:
    source = Path(project.source)
    archive = Path(os.environ.get("SSE_ARCHIVE", "/tmp/sse-archive"))
    # The entrypoint keeps root's environment, and git fails on an unreadable
    # $HOME/.gitconfig.
    env = {**os.environ, "HOME": pwd.getpwuid(os.getuid()).pw_dir}

    dialog = Dialog(archive / "dialog.jsonl")
    dialog.write(
        "init",
        data={
            "task": project.metadata.id,
            "cwd": str(source),
            "model": os.environ.get("SSE_MODEL_NAME", "none"),
            "agent": "reference",
        },
    )
    dialog.write(
        "message",
        role="assistant",
        content=(
            "Reference run: applying the task's known fix. The grade measures "
            "the task and the grader, not a model."
        ),
    )

    if not REFERENCE_PATCH.is_file():
        message = (
            f"{REFERENCE_PATCH} is missing: run this agent with "
            "`ssebench run --agent reference`"
        )
        print(f"[reference] {message}", file=sys.stderr)
        dialog.complete("error", message)
        return 1

    dialog.write(
        "tool",
        tool_id="apply",
        name="apply_patch",
        status="running",
        args={"patch": str(REFERENCE_PATCH), "cwd": str(source)},
    )
    ok, output = apply_patch(REFERENCE_PATCH, source, env)
    print(f"[reference] {output}", file=sys.stdout if ok else sys.stderr)
    if ok:
        dialog.write(
            "tool", tool_id="apply", name="apply_patch", status="success", result=output
        )
        dialog.complete("success", "Applied the reference patch")
        return 0
    dialog.write(
        "tool", tool_id="apply", name="apply_patch", status="error", error=output
    )
    dialog.complete("error", "The reference patch does not apply")
    return 1


if __name__ == "__main__":
    sys.exit(main())
