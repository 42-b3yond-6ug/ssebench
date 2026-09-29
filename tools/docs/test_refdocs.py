"""The reference pages must match the code they document; see tools/docs/reference.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from refdocs import PAGES, cli, sdk
from refdocs.page import Page, PageError


@pytest.mark.parametrize("name", PAGES)
def test_page_is_up_to_date(name: str) -> None:
    diff = PAGES[name].check()
    assert not diff, f"{PAGES[name].path} is out of date; run `just docs-gen`:\n" + "\n".join(diff[:40])


def test_a_new_cli_option_makes_the_cli_page_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    build_parser = cli.build_parser

    def with_new_option(*args: object, **kwargs: object):
        parser, extensions = build_parser()
        run = cli.subcommands(parser)
        assert run is not None
        run.choices["run"].add_argument("--new-option", help="Not documented yet")
        return parser, extensions

    monkeypatch.setattr(cli, "build_parser", with_new_option)
    assert any("--new-option" in line for line in PAGES["cli"].check())


def test_a_page_must_have_every_region(tmp_path: Path) -> None:
    page = Page("test", tmp_path / "page.md", lambda: {"one": "1", "two": "2"})
    text = "<!-- generated: one -->\n<!-- end generated -->\n<!-- generated: three -->\n<!-- end generated -->\n"
    with pytest.raises(PageError, match="missing region 'two'.*'three' is not generated"):
        _ = page.fill(text)


def test_every_sdk_module_is_listed() -> None:
    assert set(sdk.discovered_modules()) == set(sdk.MODULES) | set(sdk.UNDOCUMENTED)
