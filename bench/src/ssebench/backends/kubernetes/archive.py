"""Unpack the results that a run's container wrote, on the runner's host.

The archive directory belongs to the agent, so the tar stream it came from is not to be trusted: it may hold
absolute paths, `..`, links, devices or an enormous file. Only regular files and directories are unpacked,
below `dest`, and never through a link that is already there.
"""

import logging
import os
import stat
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import IO, Final

logger = logging.getLogger(__name__)

MAX_BYTES: Final = 2 * 1024**3
"""The most file content one unpack writes; the volumes the run wrote it to hold no more."""
MAX_MEMBERS: Final = 200_000


class UnsafeArchiveError(RuntimeError):
    """The stream cannot be unpacked without leaving `dest` or exceeding its limits."""


def _parts(name: str) -> tuple[str, ...] | None:
    """The components of a member's name, or None for the root itself. Raises for a path that leaves `dest`."""
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise UnsafeArchiveError(f"the archive holds a path outside the results: {name!r}")
    parts = tuple(part for part in path.parts if part != ".")
    return parts or None


def _make_dirs(root: Path, parts: tuple[str, ...]) -> Path:
    """Create `root/parts` one component at a time, refusing a link."""
    current = root
    for part in parts:
        current = current / part
        try:
            os.mkdir(current, 0o755)
        except FileExistsError:
            mode = os.lstat(current).st_mode
            if not stat.S_ISDIR(mode):
                raise UnsafeArchiveError(f"{current} is not a directory") from None
    return current


def unpack(source: IO[bytes], dest: Path) -> int:
    """Unpack the tar stream `source` into the directory `dest`; return the number of files written.

    Files are written as new files and renamed into place, so one that already exists is replaced whole and
    a link at its name is replaced rather than followed.

    Raises:
        UnsafeArchiveError: If a path leaves `dest`, a name clashes with a directory or a limit is exceeded.
        tarfile.TarError: If the stream is not a tar archive.
    """
    dest.mkdir(exist_ok=True)
    written = size = members = 0
    with tarfile.open(fileobj=source, mode="r|") as tar:
        for member in tar:
            members += 1
            if members > MAX_MEMBERS:
                raise UnsafeArchiveError(f"the archive holds more than {MAX_MEMBERS} entries")
            parts = _parts(member.name)
            if parts is None:
                continue
            if member.isdir():
                _ = _make_dirs(dest, parts)
            elif member.isreg():
                size += member.size
                if size > MAX_BYTES:
                    raise UnsafeArchiveError(f"the archive holds more than {MAX_BYTES} bytes")
                content = tar.extractfile(member)
                assert content is not None
                _write(dest, parts, content)
                written += 1
            else:
                logger.debug(f"Skipping {member.name}: not a file or a directory")
    return written


def _write(root: Path, parts: tuple[str, ...], content: IO[bytes]) -> None:
    parent = _make_dirs(root, parts[:-1])
    target = parent / parts[-1]
    if target.is_dir() and not target.is_symlink():
        raise UnsafeArchiveError(f"{target} is a directory")
    fd, temporary = tempfile.mkstemp(dir=parent, prefix=".unpack-")
    try:
        with os.fdopen(fd, "wb") as out:
            while chunk := content.read(1024 * 1024):
                _ = out.write(chunk)
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
