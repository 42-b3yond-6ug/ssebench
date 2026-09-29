"""`ssebench init`: set up the current directory as a workspace."""

import argparse

from ssebench import paths, workspace


def add_parser(subparsers: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    parser = subparsers.add_parser(
        "init",
        help="Write .env with generated secrets, models/ and results/ to the current directory",
        description="Sets up the current directory as a workspace, the way `just setup` does in a checkout: "
        ".env with a generated LiteLLM master key and Postgres password, a copy of the model definitions in "
        "models/ to edit, and results/. Anything that exists is left unchanged, so it is safe to run again. "
        "In a checkout, the workspace is the checkout.",
    )
    parser.set_defaults(handler=cmd_init)


def cmd_init(args: argparse.Namespace) -> int:
    root = paths.workspace()
    result = workspace.scaffold(root)
    print(f"Workspace: {root}")
    for name in result.written:
        print(f"  wrote  {name}")
    for name in result.kept:
        print(f"  kept   {name}")
    if ".env" in result.written:
        print("\n.env holds a generated LiteLLM master key and Postgres password. Never commit it.")
        print("Add the keys of the model providers you use to it; the dummy and reference agents need none.")
    print(
        "\nEdit models/ to add or change models; `ssebench run` and `ssebench proxy up` rebuild the proxy image "
        "when they change."
    )
    print("Next: `ssebench doctor` checks Docker and the rest of this host.")
    return 0
