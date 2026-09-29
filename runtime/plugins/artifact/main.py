"""Artifact plugin: write a checksummed manifest of a run's results.

A run already collects every raw artifact into the results directory: the agent
dialog (``dialog.jsonl``), the final patch (``final.patch``), the commit log,
the source snapshot and every component log, including the MCP server's. Copying
them again would only duplicate large files, so this plugin instead writes a
single index of what the run produced: for every file in the results directory,
its size and SHA-256. That gives one integrity-checkable record of the run, so a
stored or transferred result can be verified as complete and untampered without
re-reading each file.

It runs after grading, reads only the results directory, and writes only under
``artifact/`` there, so it never changes the grade.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

# Files this plugin writes; excluded from the manifest so the manifest is a
# stable index of the run's own artifacts, not of the plugin's bookkeeping.
OUTPUT_DIR = "artifact"
# The Go plugin runner's own log directory, written concurrently.
RUNNER_DIR = "plugins"


def producer(rel: str) -> str:
    """A short label for which component wrote a results file."""
    name = Path(rel).name
    if name == "dialog.jsonl":
        return "agent"
    if name in {"final.patch", "commits.log"} or name.startswith(("scriptrunner-", "patch-")):
        return "daemon"
    if name in {"result.json", "source.tar.gz"}:
        return "evaluator"
    if name.endswith(".log"):
        return "entrypoint"
    return "other"


def iter_files(archive: Path) -> list[Path]:
    """Every regular file under archive, except this plugin's own outputs and
    the plugin runner's logs, sorted for a deterministic manifest."""
    skip = {archive / OUTPUT_DIR, archive / RUNNER_DIR}
    files: list[Path] = []
    for path in archive.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if any(parent in skip for parent in path.parents):
            continue
        files.append(path)
    return sorted(files)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    archive = Path(os.environ.get("SSE_ARCHIVE", "/tmp/sse-archive"))
    if not archive.is_dir():
        print(f"[artifact] SSE_ARCHIVE {archive} is not a directory; nothing to do")
        return 0

    entries = []
    for path in iter_files(archive):
        rel = str(path.relative_to(archive))
        entries.append(
            {
                "path": rel,
                "size_bytes": path.stat().st_size,
                "sha256": sha256(path),
                "producer": producer(rel),
            }
        )

    manifest = {
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "archive": str(archive),
        "file_count": len(entries),
        "total_bytes": sum(e["size_bytes"] for e in entries),
        "files": entries,
    }

    out_dir = archive / OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"[artifact] wrote manifest of {len(entries)} files to {out_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
