"""docs/reference/cli.md: the usage and options of every `ssebench` command, from its argparse parser.

The page has one region per command that takes arguments (`cli run`, `cli dataset manifest`, ...)
and `cli commands`, the list of commands. Help strings are the option descriptions; a
"(default: ...)" in a help string becomes the Default column.
"""

from __future__ import annotations

import argparse
import re

from ssebench.cli.cli import build_parser

from .page import cell, code, prose, table

USAGE_WIDTH = 88
DEFAULT_IN_HELP = re.compile(r"\s*\(default: ([^()]*(?:\([^()]*\)[^()]*)*)\)")


def subcommands(parser: argparse.ArgumentParser) -> argparse._SubParsersAction | None:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    return None


def commands(parser: argparse.ArgumentParser, path: tuple[str, ...] = ()) -> list[tuple[str, argparse.ArgumentParser]]:
    """Every command that runs something, as (words after `ssebench`, parser), in definition order."""
    sub = subcommands(parser)
    if sub is None:
        return [(" ".join(path), parser)]
    found: list[tuple[str, argparse.ArgumentParser]] = []
    for name, child in sub.choices.items():
        found += commands(child, (*path, name))
    return found


def usage(parser: argparse.ArgumentParser) -> str:
    # A fixed width, rather than the terminal's, keeps the page the same on every machine.
    formatter = argparse.HelpFormatter(parser.prog, width=USAGE_WIDTH)
    formatter.add_usage(parser.usage, parser._actions, parser._mutually_exclusive_groups, prefix="")
    return formatter.format_help().strip()


def expand_help(action: argparse.Action) -> str:
    if not action.help or action.help == argparse.SUPPRESS:
        return ""
    params = {**vars(action), "prog": "ssebench"}
    return action.help % params


def metavar(action: argparse.Action, default: str) -> str:
    """The placeholder argparse shows for the action's value."""
    if isinstance(action.metavar, str):
        return action.metavar
    if action.choices is not None:
        return "{" + ",".join(str(c) for c in action.choices) + "}"
    return default


def option_name(action: argparse.Action) -> str:
    if not action.option_strings:
        return metavar(action, action.dest)
    names = ", ".join(action.option_strings)
    if action.nargs == 0:
        return names
    return f"{names} {metavar(action, action.dest.upper())}"


def default_cell(action: argparse.Action, help_default: str | None) -> str:
    if action.required:
        return "*(required)*"
    if help_default is not None:
        return code(help_default) if " " not in help_default else prose(help_default)
    if action.nargs == 0:
        return "off"
    if action.default in (None, "", argparse.SUPPRESS):
        return ""
    return code(str(action.default))


def description(action: argparse.Action) -> tuple[str, str | None]:
    """The help text without its "(default: ...)", and that default."""
    text = expand_help(action)
    help_default = None
    if m := DEFAULT_IN_HELP.search(text):
        help_default = m[1].strip()
        text = (text[: m.start()] + text[m.end() :]).strip()
    if action.choices is not None and not all(re.search(rf"\b{re.escape(str(c))}\b", text) for c in action.choices):
        choices = ", ".join(str(c) for c in action.choices)
        text = f"{text}. One of {choices}" if text else f"One of {choices}"
    return text, help_default


def options_table(parser: argparse.ArgumentParser) -> str:
    rows: list[list[str]] = []
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction | argparse._VersionAction | argparse._SubParsersAction):
            continue
        text, help_default = description(action)
        rows.append([code(option_name(action)), default_cell(action, help_default), prose(text)])
    if not rows:
        return "It takes no options."
    return table(["Option", "Default", "Description"], rows)


def command_region(parser: argparse.ArgumentParser) -> str:
    return f"```sh\n{usage(parser)}\n```\n\n{options_table(parser)}"


def commands_region(parser: argparse.ArgumentParser) -> str:
    rows: list[list[str]] = []

    def walk(p: argparse.ArgumentParser, path: tuple[str, ...]) -> None:
        sub = subcommands(p)
        if sub is None:
            return
        helps = {a.dest: a.help or "" for a in sub._choices_actions}
        for name, child in sub.choices.items():
            words = (*path, name)
            if subcommands(child) is None:
                rows.append([code(f"ssebench {' '.join(words)}"), cell(helps.get(name, ""))])
            walk(child, words)

    walk(parser, ())
    return table(["Command", "Description"], rows)


def regions() -> dict[str, str]:
    parser, _ = build_parser()
    found = {"cli commands": commands_region(parser)}
    for words, command in commands(parser):
        found[f"cli {words}"] = command_region(command)
    return found
