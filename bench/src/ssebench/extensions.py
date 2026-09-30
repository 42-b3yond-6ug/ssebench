"""Extend SSEBench from another package, without forking it.

An installed package registers tool layers, runner backends and CLI subcommands as entry points,
for example in its pyproject.toml:

    [project.entry-points."ssebench.tool_layers"]
    my-layer = "my_package.layers:MyToolLayer"

    [project.entry-points."ssebench.backends"]
    my-backend = "my_package.backend:MyBackend"

    [project.entry-points."ssebench.commands"]
    my-command = "my_package.cli:MyCommand"

The entry-point name is the name users type: `ssebench run --tool-layer my-layer`,
`ssebench run --backend my-backend` and `ssebench my-command`. This module is the stable import location for everything an extension
needs; the contract is documented in docs/guides/extension-points.md.
"""

import argparse
import logging
from collections.abc import Collection, Mapping
from importlib.metadata import EntryPoint, entry_points
from types import MappingProxyType
from typing import Final, Protocol, runtime_checkable

from ssebench.backends import (
    Backend,
    BackendError,
    DockerBackend,
    ImageRequest,
    Images,
    ImageUnavailableError,
    Mount,
    NetworkPolicy,
    RunHandle,
    RunInfo,
    RunSpec,
    SidecarPair,
    prebuilt_images,
)
from ssebench.middleware import SandboxToolLayer, ToolLayer, ToolLayerContext
from ssebench.pipe import REGISTRY, TAG

__all__ = [
    "BACKENDS_GROUP",
    "BUILTIN_BACKENDS",
    "BUILTIN_TOOL_LAYERS",
    "COMMANDS_GROUP",
    "DEFAULT_BACKEND",
    "DEFAULT_TOOL_LAYER",
    "REGISTRY",
    "TAG",
    "TOOL_LAYERS_GROUP",
    "Backend",
    "BackendError",
    "Command",
    "DockerBackend",
    "ExtensionError",
    "ImageRequest",
    "ImageUnavailableError",
    "Images",
    "Mount",
    "NetworkPolicy",
    "RunHandle",
    "RunInfo",
    "RunSpec",
    "SandboxToolLayer",
    "SidecarPair",
    "ToolLayer",
    "ToolLayerContext",
    "backend_names",
    "command_names",
    "get_backend",
    "get_tool_layer",
    "load_commands",
    "prebuilt_images",
    "tool_layer_names",
]

logger = logging.getLogger(__name__)

TOOL_LAYERS_GROUP: Final = "ssebench.tool_layers"
COMMANDS_GROUP: Final = "ssebench.commands"
BACKENDS_GROUP: Final = "ssebench.backends"

DEFAULT_TOOL_LAYER: Final = "sandbox"
BUILTIN_TOOL_LAYERS: Final[Mapping[str, type[ToolLayer]]] = MappingProxyType({DEFAULT_TOOL_LAYER: SandboxToolLayer})

DEFAULT_BACKEND: Final = "docker"
BUILTIN_BACKENDS: Final[Mapping[str, type[Backend]]] = MappingProxyType({DEFAULT_BACKEND: DockerBackend})


class ExtensionError(RuntimeError):
    """A selected extension is unknown, registered more than once, or does not implement its interface."""


@runtime_checkable
class Command(Protocol):
    """A CLI subcommand, run as `ssebench <name>`.

    Register the class, or an instance, under the `ssebench.commands` entry-point group. A class
    is instantiated without arguments.
    """

    name: str
    """The subcommand; it must equal the entry-point name."""

    help: str
    """One line, shown by `ssebench --help`."""

    def configure(self, parser: argparse.ArgumentParser) -> None:
        """Add the subcommand's arguments to `parser`. It may be called more than once."""
        ...

    def run(self, args: argparse.Namespace) -> int:
        """Run the subcommand with the parsed arguments and return the exit status."""
        ...


def _registered(group: str) -> dict[str, list[EntryPoint]]:
    found: dict[str, list[EntryPoint]] = {}
    for entry_point in entry_points(group=group):
        found.setdefault(entry_point.name, []).append(entry_point)
    return found


def _origin(entry_point: EntryPoint) -> str:
    dist = entry_point.dist.name if entry_point.dist else "an unknown distribution"
    return f"{entry_point.value} from {dist}"


def tool_layer_names() -> list[str]:
    """The names `ssebench run --tool-layer` accepts: the built-in layers and the registered ones."""
    return sorted({*BUILTIN_TOOL_LAYERS, *_registered(TOOL_LAYERS_GROUP)})


def get_tool_layer(name: str) -> type[ToolLayer]:
    """Return the tool layer class called `name`.

    Raises ExtensionError if no layer or more than one layer has that name, or if the registered
    object cannot be imported or is not a ToolLayer subclass. Only the selected entry point is
    imported.
    """
    registered = _registered(TOOL_LAYERS_GROUP).get(name, [])
    claims = [_origin(entry_point) for entry_point in registered]
    if name in BUILTIN_TOOL_LAYERS:
        claims.insert(0, "the built-in layer")
    if len(claims) > 1:
        raise ExtensionError(
            f"Tool layer {name!r} is registered more than once: {'; '.join(claims)}. Uninstall or rename all but one."
        )

    if name in BUILTIN_TOOL_LAYERS:
        return BUILTIN_TOOL_LAYERS[name]
    if not registered:
        raise ExtensionError(f"Unknown tool layer {name!r}. Available: {', '.join(tool_layer_names())}.")

    entry_point = registered[0]
    try:
        layer = entry_point.load()
    except Exception as e:
        raise ExtensionError(f"Cannot load tool layer {name!r} ({_origin(entry_point)}): {e}") from e
    if not (isinstance(layer, type) and issubclass(layer, ToolLayer)):
        raise ExtensionError(
            f"Tool layer {name!r} ({_origin(entry_point)}) is not a subclass of ssebench.extensions.ToolLayer."
        )
    return layer


def backend_names() -> list[str]:
    """The names `ssebench run --backend` accepts: the built-in backend and the registered ones."""
    return sorted({*BUILTIN_BACKENDS, *_registered(BACKENDS_GROUP)})


def get_backend(name: str) -> Backend:
    """Return a runner backend called `name`, created without arguments.

    Raises ExtensionError if no backend or more than one backend has that name, or if the registered
    object cannot be imported, is not a Backend subclass or cannot be created. Only the selected entry
    point is imported.
    """
    registered = _registered(BACKENDS_GROUP).get(name, [])
    claims = [_origin(entry_point) for entry_point in registered]
    if name in BUILTIN_BACKENDS:
        claims.insert(0, "the built-in backend")
    if len(claims) > 1:
        raise ExtensionError(
            f"Backend {name!r} is registered more than once: {'; '.join(claims)}. Uninstall or rename all but one."
        )

    if name in BUILTIN_BACKENDS:
        return BUILTIN_BACKENDS[name]()
    if not registered:
        raise ExtensionError(f"Unknown backend {name!r}. Available: {', '.join(backend_names())}.")

    entry_point = registered[0]
    try:
        backend = entry_point.load()
    except Exception as e:
        raise ExtensionError(f"Cannot load backend {name!r} ({_origin(entry_point)}): {e}") from e
    if not (isinstance(backend, type) and issubclass(backend, Backend)):
        raise ExtensionError(
            f"Backend {name!r} ({_origin(entry_point)}) is not a subclass of ssebench.extensions.Backend."
        )
    try:
        return backend()
    except Exception as e:
        raise ExtensionError(f"Cannot create backend {name!r} ({_origin(entry_point)}): {e}") from e


def command_names() -> list[str]:
    """The names registered under the `ssebench.commands` group, without importing them."""
    return sorted(_registered(COMMANDS_GROUP))


def load_commands(name: str | None = None, *, reserved: Collection[str] = ()) -> list[Command]:
    """Import the registered commands, or only the one called `name`.

    A command is skipped with a warning when its name is in `reserved` or registered more than
    once, or when it fails to import or does not implement Command. One broken extension
    therefore cannot break the CLI.
    """
    commands: list[Command] = []
    for command_name, registered in sorted(_registered(COMMANDS_GROUP).items()):
        if name is not None and command_name != name:
            continue
        origins = "; ".join(_origin(entry_point) for entry_point in registered)
        if command_name in reserved:
            logger.warning(f"Ignoring command {command_name!r} ({origins}): a built-in command has that name")
            continue
        if len(registered) > 1:
            logger.warning(f"Ignoring command {command_name!r}: it is registered more than once ({origins})")
            continue

        try:
            loaded: object = registered[0].load()
            command: object = loaded() if isinstance(loaded, type) else loaded
        except Exception as e:
            logger.warning(f"Ignoring command {command_name!r} ({origins}): cannot load it: {e}")
            continue
        if not isinstance(command, Command):
            logger.warning(
                f"Ignoring command {command_name!r} ({origins}): it does not implement ssebench.extensions.Command"
            )
            continue
        if command.name != command_name:
            logger.warning(f"Ignoring command {command_name!r} ({origins}): the command calls itself {command.name!r}")
            continue
        commands.append(command)
    return commands
