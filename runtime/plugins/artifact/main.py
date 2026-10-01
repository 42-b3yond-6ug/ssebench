"""Artifact plugin: write a checksummed manifest of a run's results.

A run already collects every raw artifact into the results directory: the agent
dialog (``archive/dialog.jsonl``), the final patch (``final.patch``), the commit
log, the source snapshot and every component log, including the MCP server's.
Copying them again would only duplicate large files, so this plugin instead
writes a single index of what the run produced: for every file in the results
directory, its size and SHA-256. That gives one integrity-checkable record of
the run, so a stored or transferred result can be verified as complete and
untampered without re-reading each file.

It runs after grading, reads only the results directory (``SSE_RESULTS``) and
the agent's archive (``SSE_ARCHIVE``), and writes only under ``artifact/`` in
the archive, so it never changes the grade.
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
# The archive's place in the run directory, which the CLI assembles on the host.
ARCHIVE_DIR = "archive"


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


def dir_id(path: Path) -> tuple[int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return st.st_dev, st.st_ino


def iter_files(root: Path, skip: set[tuple[int, int]], seen: set[tuple[int, int]]) -> list[Path]:
    """Every regular file under root, sorted for a deterministic manifest.

    Directories are compared by device and inode, not by path: in the sandbox
    the archive is mounted both at SSE_ARCHIVE and inside SSE_RESULTS. The
    directories in ``skip`` are left out; every directory walked is added to
    ``seen``.
    """
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        ident = dir_id(current)
        if ident is not None:
            seen.add(ident)
        dirnames[:] = sorted(d for d in dirnames if dir_id(current / d) not in skip)
        for name in filenames:
            path = current / name
            if path.is_file() and not path.is_symlink():
                files.append(path)
    return sorted(files)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def report_skipped(reason: str) -> None:
    print(f"[artifact] {reason}; skipping")
    skip_file = os.environ.get("SSE_PLUGIN_SKIP_FILE")
    if skip_file:
        Path(skip_file).write_text(reason + "\n")


def main() -> int:
    results = Path(os.environ.get("SSE_RESULTS", "/var/lib/ssebench/results"))
    archive = Path(os.environ.get("SSE_ARCHIVE", "/tmp/sse-archive"))
    if not results.is_dir():
        report_skipped(f"SSE_RESULTS {results} is not a directory")
        return 0

    out_dir = archive / OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    skip = {i for i in (dir_id(out_dir), dir_id(archive / RUNNER_DIR)) if i is not None}

    seen: set[tuple[int, int]] = set()
    files = [(path, path.relative_to(results).as_posix()) for path in iter_files(results, skip, seen)]
    # On Kubernetes the archive is a volume of its own, not part of the results
    # directory; the CLI puts it in the run directory's archive/ afterwards.
    if dir_id(archive) not in seen:
        files += [
            (path, f"{ARCHIVE_DIR}/{path.relative_to(archive).as_posix()}") for path in iter_files(archive, skip, seen)
        ]

    entries = [
        {
            "path": rel,
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
            "producer": producer(rel),
        }
        for path, rel in files
    ]

    manifest = {
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "results": str(results),
        "file_count": len(entries),
        "total_bytes": sum(e["size_bytes"] for e in entries),
        "files": entries,
    }

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"[artifact] wrote manifest of {len(entries)} files to {out_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
