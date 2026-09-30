"""Unpacking results that an untrusted container produced."""

import io
import tarfile
from pathlib import Path

import pytest

from ssebench.backends.kubernetes import archive


def make_tar(*members: tarfile.TarInfo, contents: dict[str, bytes] | None = None) -> io.BytesIO:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for member in members:
            data = (contents or {}).get(member.name)
            if data is not None:
                member.size = len(data)
                tar.addfile(member, io.BytesIO(data))
            else:
                tar.addfile(member)
    _ = buffer.seek(0)
    return buffer


def regular(name: str) -> tarfile.TarInfo:
    return tarfile.TarInfo(name)


def special(name: str, kind: bytes, target: str = "") -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type, info.linkname = kind, target
    return info


def test_files_and_directories_are_unpacked_with_plain_permissions(tmp_path: Path) -> None:
    directory = special("logs", tarfile.DIRTYPE)
    stream = make_tar(
        directory, regular("logs/a.log"), regular("./top.txt"), contents={"logs/a.log": b"a", "./top.txt": b"t"}
    )

    assert archive.unpack(stream, tmp_path) == 2

    assert (tmp_path / "logs" / "a.log").read_bytes() == b"a"
    assert (tmp_path / "top.txt").read_bytes() == b"t"
    assert (tmp_path / "top.txt").stat().st_mode & 0o777 == 0o644


def test_an_existing_file_is_replaced_and_a_link_at_its_name_is_not_followed(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    _ = outside.write_text("keep")
    dest = tmp_path / "run"
    dest.mkdir()
    (dest / "result.json").symlink_to(outside)

    _ = archive.unpack(make_tar(regular("result.json"), contents={"result.json": b"new"}), dest)

    assert outside.read_text() == "keep"
    assert (dest / "result.json").read_bytes() == b"new" and not (dest / "result.json").is_symlink()


def test_a_directory_that_is_a_link_in_the_destination_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    dest = tmp_path / "run"
    dest.mkdir()
    (dest / "archive").symlink_to(outside)

    with pytest.raises(archive.UnsafeArchiveError, match="not a directory"):
        _ = archive.unpack(make_tar(regular("archive/x"), contents={"archive/x": b"x"}), dest)

    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("name", ["../escape", "a/../../escape", "/etc/escape"])
def test_paths_that_leave_the_destination_are_refused(tmp_path: Path, name: str) -> None:
    dest = tmp_path / "run"
    dest.mkdir()

    with pytest.raises(archive.UnsafeArchiveError, match="outside the results"):
        _ = archive.unpack(make_tar(regular(name), contents={name: b"x"}), dest)

    assert not (tmp_path / "escape").exists()


def test_links_devices_and_pipes_are_skipped(tmp_path: Path) -> None:
    stream = make_tar(
        special("sym", tarfile.SYMTYPE, "/etc/passwd"),
        special("hard", tarfile.LNKTYPE, "ok.txt"),
        special("null", tarfile.CHRTYPE),
        special("fifo", tarfile.FIFOTYPE),
        regular("ok.txt"),
        contents={"ok.txt": b"ok"},
    )

    assert archive.unpack(stream, tmp_path) == 1

    assert sorted(p.name for p in tmp_path.iterdir()) == ["ok.txt"]


def test_a_file_over_the_size_limit_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(archive, "MAX_BYTES", 10)

    with pytest.raises(archive.UnsafeArchiveError, match="more than 10 bytes"):
        _ = archive.unpack(make_tar(regular("big"), contents={"big": b"x" * 11}), tmp_path)


def test_too_many_entries_are_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(archive, "MAX_MEMBERS", 2)
    names = ["a", "b", "c"]

    with pytest.raises(archive.UnsafeArchiveError, match="more than 2 entries"):
        _ = archive.unpack(make_tar(*[regular(n) for n in names], contents=dict.fromkeys(names, b"")), tmp_path)
