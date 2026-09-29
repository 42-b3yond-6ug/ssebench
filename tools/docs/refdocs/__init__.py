"""Generators for the reference pages in docs/reference/; see tools/docs/reference.py."""

from __future__ import annotations

from pathlib import Path

from . import cli, config, daemon, env, sdk
from .page import Page

PAGES: dict[str, Page] = {
    page.name: page
    for page in [
        Page("cli", Path("docs/reference/cli.md"), cli.regions),
        Page("python-sdk", Path("docs/reference/python-sdk.md"), sdk.regions),
        Page("daemon-api", Path("docs/reference/daemon-api.md"), daemon.regions),
        Page("environment", Path("docs/reference/environment.md"), env.regions),
        Page("configuration", Path("docs/reference/configuration.md"), config.regions),
        Page("extension-points", Path("docs/guides/extension-points.md"), env.contract_regions),
    ]
}
