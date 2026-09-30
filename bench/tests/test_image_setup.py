"""The scripts that prepare an image for the unprivileged runner."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

COMMON = Path(__file__).resolve().parents[2] / "images" / "common"
SHARE = COMMON / "share-build-caches.sh"


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def share(monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
    for name in ("CARGO_HOME", "RUSTUP_HOME", "GOPATH"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    _ = subprocess.run(["sh", str(SHARE)], check=True, capture_output=True)


@pytest.fixture
def cargo_home(tmp_path: Path) -> Path:
    """A registry with a crate that was unpacked as `fnv` is: files nobody but the owner and group can read."""
    crate = tmp_path / "cargo" / "registry" / "src" / "index" / "fnv-1.0.7"
    crate.mkdir(parents=True)
    _ = (crate / "lib.rs").write_text("pub struct FnvHasher;\n")
    _ = (crate / "Cargo.toml").write_text("[package]\n")
    crate.chmod(0o750)
    (crate / "lib.rs").chmod(0o640)
    (crate / "Cargo.toml").chmod(0o644)
    return tmp_path / "cargo"


def test_crate_files_become_readable_to_every_user(monkeypatch: pytest.MonkeyPatch, cargo_home: Path) -> None:
    crate = cargo_home / "registry" / "src" / "index" / "fnv-1.0.7"

    share(monkeypatch, CARGO_HOME=str(cargo_home))

    assert mode(crate / "lib.rs") == 0o644
    assert mode(crate) == 0o755
    assert mode(crate / "Cargo.toml") == 0o644


def test_only_read_access_is_added(monkeypatch: pytest.MonkeyPatch, cargo_home: Path) -> None:
    private = cargo_home / "registry" / "token"
    _ = private.write_text("secret\n")
    private.chmod(0o600)

    share(monkeypatch, CARGO_HOME=str(cargo_home))

    assert mode(private) == 0o604
    assert not mode(private) & stat.S_IWOTH


def test_every_named_directory_is_covered(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    files: dict[str, Path] = {}
    for name in ("RUSTUP_HOME", "GOPATH"):
        directory = tmp_path / name
        directory.mkdir()
        files[name] = directory / "file"
        _ = files[name].write_text("x")
        files[name].chmod(0o640)

    share(monkeypatch, **{name: str(path.parent) for name, path in files.items()})

    assert [mode(path) for path in files.values()] == [0o644, 0o644]


def test_other_directories_are_left_alone(monkeypatch: pytest.MonkeyPatch, cargo_home: Path, tmp_path: Path) -> None:
    other = tmp_path / "home"
    other.mkdir()
    secret = other / "id_rsa"
    _ = secret.write_text("key\n")
    secret.chmod(0o600)

    share(monkeypatch, CARGO_HOME=str(cargo_home))

    assert mode(secret) == 0o600


def test_no_toolchain_variable_is_no_error(monkeypatch: pytest.MonkeyPatch) -> None:
    share(monkeypatch)


def test_setup_source_shares_the_caches() -> None:
    assert "share-build-caches.sh" in (COMMON / "setup-source.sh").read_text()
    assert os.access(SHARE, os.X_OK)


@pytest.mark.parametrize("image", ["sandbox", "sidecar-case"])
def test_the_images_bring_the_whole_setup_directory(image: str) -> None:
    dockerfile = (COMMON.parent / image / "Dockerfile").read_text()

    assert "COPY --chmod=755 images/common/ /tmp/image-setup/" in dockerfile
    assert "/tmp/image-setup/setup-source.sh" in dockerfile
