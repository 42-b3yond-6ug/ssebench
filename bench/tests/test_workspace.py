"""`ssebench init` sets up a workspace and never overwrites what is there."""

import re
import stat
from pathlib import Path

import pytest

from ssebench import paths, workspace
from ssebench.cli.cli import main

CHECKOUT = Path(__file__).resolve().parents[2]
TEMPLATE = "# comment\nLITELLM_MASTER_KEY=\nPOSTGRES_PASSWORD=\nANTHROPIC_API_KEY=\n# LITELLM_PORT=4000\n"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    (home / "models").mkdir(parents=True)
    _ = (home / "pyproject.toml").write_text("[tool.ssebench]\n")
    _ = (home / ".env.example").write_text(TEMPLATE)
    _ = (home / "models" / "a.yaml").write_text("- model_name: a\n")
    _ = (home / "models" / "b.yml").write_text("- model_name: b\n")
    _ = (home / "models" / "README.md").write_text("not a model file\n")
    monkeypatch.setenv(paths.HOME_ENV, str(home))
    return home


def values(env: str) -> dict[str, str]:
    """The `NAME=value` lines of a .env file."""
    return dict(line.split("=", 1) for line in env.splitlines() if re.match(r"[A-Z_]+=", line))


def test_the_secrets_are_generated(home: Path, tmp_path: Path) -> None:
    result = workspace.scaffold(tmp_path / "work")

    env = values((tmp_path / "work" / ".env").read_text())
    assert re.fullmatch(r"sk-[0-9a-f]{48}", env["LITELLM_MASTER_KEY"])
    assert re.fullmatch(r"[0-9a-f]{48}", env["POSTGRES_PASSWORD"])
    assert env["ANTHROPIC_API_KEY"] == ""
    assert ".env" in result.written


def test_the_secrets_differ_between_workspaces(home: Path, tmp_path: Path) -> None:
    _ = workspace.scaffold(tmp_path / "one")
    _ = workspace.scaffold(tmp_path / "two")

    assert values((tmp_path / "one" / ".env").read_text()) != values((tmp_path / "two" / ".env").read_text())


def test_only_the_secrets_change(home: Path, tmp_path: Path) -> None:
    _ = workspace.scaffold(tmp_path / "work")

    lines = (tmp_path / "work" / ".env").read_text().splitlines()
    assert [line for line in lines if not re.match(r"(LITELLM_MASTER_KEY|POSTGRES_PASSWORD)=", line)] == [
        "# comment",
        "ANTHROPIC_API_KEY=",
        "# LITELLM_PORT=4000",
    ]


def test_env_is_readable_by_its_owner_only(home: Path, tmp_path: Path) -> None:
    _ = workspace.scaffold(tmp_path / "work")

    assert stat.S_IMODE((tmp_path / "work" / ".env").stat().st_mode) == 0o600


def test_models_are_copied_for_editing(home: Path, tmp_path: Path) -> None:
    _ = workspace.scaffold(tmp_path / "work")

    assert sorted(p.name for p in (tmp_path / "work" / "models").iterdir()) == ["a.yaml", "b.yml"]
    assert (tmp_path / "work" / "results").is_dir()


def test_nothing_that_exists_is_changed(home: Path, tmp_path: Path) -> None:
    work = tmp_path / "work"
    _ = workspace.scaffold(work)
    env = (work / ".env").read_text()
    _ = (work / "models" / "a.yaml").write_text("- model_name: edited\n")
    (work / "models" / "b.yml").unlink()
    _ = (home / "models" / "c.yaml").write_text("- model_name: c\n")

    result = workspace.scaffold(work)

    assert (work / ".env").read_text() == env
    assert (work / "models" / "a.yaml").read_text() == "- model_name: edited\n"
    # A model file the workspace lacks, such as one a newer release added, is copied.
    assert sorted(result.written) == ["models/b.yml", "models/c.yaml"]
    assert ".env" in result.kept
    assert "models/a.yaml" in result.kept


def test_the_template_of_the_repository_has_both_secrets() -> None:
    env = values(workspace.render_env((CHECKOUT / ".env.example").read_text()))

    assert env["LITELLM_MASTER_KEY"].startswith("sk-")
    assert len(env["POSTGRES_PASSWORD"]) == 48


def test_init_in_a_package_install_writes_to_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    package = tmp_path / "site-packages" / "ssebench"
    data = package / "_data"
    (data / "models").mkdir(parents=True)
    _ = (data / "pyproject.toml").write_text("[tool.ssebench]\n")
    _ = (data / ".env.example").write_text(TEMPLATE)
    _ = (data / "models" / "a.yaml").write_text("- model_name: a\n")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(paths, "__file__", str(package / "paths.py"))
    monkeypatch.delenv(paths.HOME_ENV, raising=False)
    monkeypatch.chdir(work)

    with pytest.raises(SystemExit) as exit_info:
        main(["init"])

    assert exit_info.value.code == 0
    assert sorted(p.name for p in work.iterdir()) == [".env", "models", "results"]
    assert sorted(p.name for p in data.iterdir()) == [".env.example", "models", "pyproject.toml"]
    out = capsys.readouterr().out
    assert f"Workspace: {work.resolve()}" in out
    assert "wrote  .env" in out


def test_init_in_a_checkout_uses_the_checkout(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    with pytest.raises(SystemExit) as exit_info:
        main(["init"])

    assert exit_info.value.code == 0
    assert (home / ".env").is_file()
    assert list(elsewhere.iterdir()) == []
    assert "kept   models/a.yaml" in capsys.readouterr().out
