"""The interface between the runner and the place where a run's containers execute.

The runner decides what a run is: the images, the environment, the files and the labels of its
containers, and how its results are recorded. A `Backend` carries that out on a container platform.
`DockerBackend` runs on the local Docker daemon; another backend can run the same `RunSpec` elsewhere,
for example as a Job on Kubernetes. The contract is documented in docs/concepts/runner-backends.md.

This module imports nothing from the runner, so an extension can depend on it alone.
"""

import logging
import shlex
from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, ClassVar, Final, Literal
from uuid import uuid4

from ssebench.errors import UserError

if TYPE_CHECKING:
    from ssebench.agents import Agent
    from ssebench.middleware import ToolLayer
    from ssebench.tasks import Task

logger = logging.getLogger(__name__)

Mode = Literal["sandbox", "sidecar"]
Egress = Literal["restricted", "open"]
MountKind = Literal["bind", "volume"]
RunState = Literal["created", "running", "exited", "unknown"]

# ==================== the container contract ====================

ARCHIVE_PATH: Final = "/tmp/sse-archive"
"""Where a task container has the agent's archive (`SSE_ARCHIVE`): the run directory's `archive/`."""
RESULTS_PATH: Final = "/var/lib/ssebench/results"
"""Where a task container has the run directory: root-only, for the grade, the graded patch and the logs."""
SIDECAR_SOCKET_DIR: Final = "/run/ssebench"
"""Where both containers of a sidecar run mount the volume that holds the daemon's sockets."""
SIDECAR_DAEMON_SOCKET: Final = f"{SIDECAR_SOCKET_DIR}/sse.sock"

STOP_GRACE_SECONDS: Final = 20
"""How long `stop` waits for the entrypoint to clean up before it kills the container."""

# ==================== labels ====================

RUN_ID_LABEL: Final = "ssebench.run-id"
"""Label with the run's ID: the caller's `--run-id`, else the generated one."""
RESULTS_LABEL: Final = "ssebench.results"
"""Label with the run's own directory on the runner's host, for the web UI."""
WEBUI_LABEL: Final = "ssebench.webui"
TASK_LABEL: Final = "ssebench.task-id"
MODEL_LABEL: Final = "ssebench.model"
AGENT_LABEL: Final = "ssebench.agent"
PAIR_LABEL: Final = "ssebench.run"
"""Label of every container and volume of a sidecar pair, with the pair's own ID."""


class BackendError(RuntimeError):
    """The backend could not start, watch or stop a run. The message is safe to show: it carries no secret."""


class ImageUnavailableError(UserError):
    """A prebuilt image is in neither the registry nor the local image store."""


# ==================== images ====================


@dataclass(frozen=True, kw_only=True)
class ImageRequest:
    """The images a run needs.

    With `prebuilt` the images are the published ones, named by `prebuilt_images`, and are only made
    available. Without it the backend builds the layers of the run from the task, the tool layer and the agent.
    """

    mode: Mode
    task: "Task"
    agent: "Agent"
    tool_layer: "type[ToolLayer] | None" = None
    """The tool layer to build in sandbox mode; sidecar mode has its own."""
    plugins: tuple[str, ...] = ()
    """Plugins to install into the tool layer, by folder name."""
    prebuilt: bool = False


@dataclass(frozen=True, kw_only=True)
class Images:
    """The images of a prepared run."""

    agent: str
    """The image of the container the run waits on: in sandbox mode the whole run (case, tool and agent
    layers), in sidecar mode the agent runtime."""
    environment: str | None = None
    """Sidecar mode only: the image of the task container, which holds the daemon."""

    def task_image(self) -> str:
        """The image that holds the task's own files, `/ssebench` among them."""
        return self.environment or self.agent


# ==================== the model proxy ====================


@dataclass(frozen=True, kw_only=True)
class ProxyEndpoint:
    """The LiteLLM proxy of a backend that has one of its own, as two URLs.

    The runner creates each run's key through `host_url` and gives the run `service_url`, so the URLs
    differ when the run's containers reach the proxy by another name than the runner does.
    """

    host_url: str
    """Where the runner reaches the proxy, to create and read the run's key."""
    service_url: str
    """Where the run's container reaches the proxy: its `SSE_BASE_URL`."""


# ==================== run specification ====================


@dataclass(frozen=True, kw_only=True)
class Mount:
    """A file or directory of the runner, or a volume, at a path in a container."""

    target: str
    """Absolute path in the container."""
    source: str
    """A path on the runner's host for `bind`; a volume name for `volume`."""
    kind: MountKind = "bind"
    read_only: bool = False


@dataclass(frozen=True, kw_only=True)
class NetworkPolicy:
    """What a run's containers may reach."""

    egress: Egress = "restricted"
    """`restricted` reaches the model proxy and nothing else; `open` also has internet access."""


@dataclass(frozen=True, kw_only=True)
class SidecarPair:
    """The two containers of a sidecar run and what they share.

    The environment container is the case image with the daemon; the agent container is the runtime image
    with the agent, the MCP server and the evaluator. They share the project's source tree, the run
    directory and a root-owned directory with the daemon's sockets. The task's `/ssebench` (reference patch,
    hidden tests, scripts) stays in the environment container.
    """

    task_name: str
    source_dir: str
    """Absolute path of the project source, the same in both containers."""
    environment_image: str
    difficulty: int
    keep_alive: bool = False
    run_id: str = field(default_factory=lambda: uuid4().hex[:12])
    """Identifies this pair's containers and volumes, which carry it as the `ssebench.run` label."""

    @property
    def environment_name(self) -> str:
        return f"ssebench-env-{self.task_name.lower()}-{self.run_id}"

    @property
    def source_volume(self) -> str:
        return f"ssebench-{self.run_id}-source"

    @property
    def socket_volume(self) -> str:
        return f"ssebench-{self.run_id}-sockets"

    @property
    def volumes(self) -> tuple[str, str]:
        """The run-scoped volumes: the backend creates them before the containers start and removes them after."""
        return (self.source_volume, self.socket_volume)

    def shared_env(self) -> dict[str, str]:
        """The environment of both containers."""
        return {
            "SSE_ARCHIVE": ARCHIVE_PATH,
            "SSE_DAEMON_SOCKET": SIDECAR_DAEMON_SOCKET,
            # The daemon enforces the difficulty gate; the agent container's MCP server mirrors it.
            "SSE_DIFFICULTY": str(self.difficulty),
            "SSE_RESULTS": RESULTS_PATH,
        }

    def environment_env(self) -> dict[str, str]:
        """The environment of the environment container alone."""
        return {"SSE_KEEP_ALIVE": "1" if self.keep_alive else "0"}

    def shared_mounts(self, results: Mount, archive: Mount) -> list[Mount]:
        """What both containers mount, given the run directory's mounts."""
        return [
            archive,
            Mount(target=self.source_dir, source=self.source_volume, kind="volume"),
            Mount(target=SIDECAR_SOCKET_DIR, source=self.socket_volume, kind="volume"),
            results,
        ]


@dataclass(frozen=True, kw_only=True)
class RunSpec:
    """Everything a backend needs to start a run.

    A sandbox run is one container. A sidecar run is the container of `sidecar.environment_image`, started
    first and left running, and the container of `image`, which the run waits for.
    """

    run_id: str
    mode: Mode
    task_name: str
    image: str
    """The image of the container the run waits for."""
    env: Mapping[str, str] = field(repr=False)
    """Environment of that container. It holds the run's model key, so it is left out of the repr."""
    results: Mount
    """The run directory, at `RESULTS_PATH`. Root-only in the container."""
    archive: Mount
    """The run directory's `archive/`, at `ARCHIVE_PATH`: the agent's own files."""
    network: NetworkPolicy
    labels: Mapping[str, str]
    """Labels of the container the web UI lists: the task container, or the environment container of a pair."""
    timeout: int
    """How long the agent may run, in seconds. The container enforces it itself; a backend may use it to set
    a deadline of its own."""
    artifacts: tuple[Mount, ...] = ()
    """Read-only files for the container, such as the reference patch. `source` is on the runner's host."""
    platform: str | None = None
    """The `linux/<arch>` platform of every image and container of the run; None takes the backend's own."""
    keep: bool = False
    """Leave the containers and volumes in place when the run ends, so they can be inspected."""
    sidecar: SidecarPair | None = None

    def __post_init__(self) -> None:
        if (self.mode == "sidecar") != (self.sidecar is not None):
            raise ValueError("a sidecar run needs a SidecarPair, and no other run has one")


# ==================== a started run ====================


@dataclass(kw_only=True)
class RunHandle:
    """A run that was started, or found. A backend subclasses it for what it needs to control the run."""

    run_id: str
    name: str = ""
    """What identifies the run to the backend, such as a container name or a Job name."""
    keep: bool = False


@dataclass(frozen=True, kw_only=True)
class RunInfo:
    """A run as `list_runs` and `inspect_run` report it."""

    run_id: str
    name: str
    state: RunState
    exit_code: int | None
    image: str
    labels: Mapping[str, str]
    handle: RunHandle
    """For `stop`, `logs`, `wait` and `cleanup`."""
    created_at: str | None = None
    """When the run's container was created, as an ISO 8601 timestamp, if the backend knows."""


class Backend(ABC):
    """Where a run's images are prepared and its containers execute.

    A backend keeps no state of its own between calls: what it needs to control a run is in the `RunHandle`,
    and it finds runs again by their labels. One instance serves any number of runs, from any thread.
    """

    name: ClassVar[str]
    """The name users select with `ssebench run --backend`."""

    builds_images: bool = False
    """Whether `prepare_images` can build the layers of a run. A backend without it needs `prebuilt=True`."""

    supports_exec: bool = False
    """Whether `exec_argv` works, which is what the web UI's terminal and assistant need."""

    def proxy(self) -> ProxyEndpoint | None:
        """The backend's own LiteLLM proxy, or None for the local Compose stack, which `ssebench run` starts.

        A backend that returns an endpoint is responsible for the proxy being up; the runner starts nothing.
        The admin key is still the `LITELLM_MASTER_KEY` setting.
        """
        return None

    @abstractmethod
    def prepare_images(self, request: ImageRequest) -> Images:
        """Make the images of the run available to the backend, and return their names.

        With `request.prebuilt` this pulls the published images, or checks that the backend can pull them.
        Without it, this builds the layers.

        Raises:
            UserError: If a layer fails to build or a prebuilt image cannot be found.
        """

    @abstractmethod
    def copy_from_image(self, image: str, path: PurePosixPath, dest: Path, platform: str | None = None) -> None:
        """Copy one file out of an image without starting the run, for the reference patch.

        Raises:
            RuntimeError: If the file cannot be copied.
        """

    @abstractmethod
    def start(self, spec: RunSpec) -> RunHandle:
        """Start the run and return once its containers exist.

        From here on the container's output is forwarded to this process's stdout and stderr as it is
        written; `logs` reads it back afterwards. When this raises, nothing of the run is left behind.

        Raises:
            BackendError: If the run cannot be started.
        """

    @abstractmethod
    def wait(self, handle: RunHandle, timeout: float | None = None) -> int:
        """Wait until the container the run waits for exits, and return its exit status.

        A container that was stopped ends with 128 plus the signal, 143 for the SIGTERM of `stop`.

        Raises:
            TimeoutError: If it is still running after `timeout` seconds.
        """

    @abstractmethod
    def logs(self, handle: RunHandle, *, follow: bool = False) -> Iterator[str]:
        """The lines of the container's output, stdout and stderr together; with `follow`, until it exits.

        Raises:
            BackendError: If the output is gone, for example because the container was removed.
        """

    @abstractmethod
    def collect_results(self, handle: RunHandle, dest: Path) -> None:
        """Put the run's results in `dest`, the run directory on the runner's host, once the run has exited.

        The results are the files the container wrote to `RESULTS_PATH` and `ARCHIVE_PATH`: `result.json`,
        the logs and `archive/`. `dest` already holds the skeleton the runner made, and the files that the
        container wrote are theirs to replace. A backend whose containers share a file system with the
        runner, as Docker does with a bind mount, has nothing to do.

        Raises:
            BackendError: If the results cannot be fetched.
        """

    @abstractmethod
    def stop(self, handle: RunHandle, grace: int = STOP_GRACE_SECONDS) -> None:
        """Ask the run's containers to stop, and kill them after `grace` seconds. Safe to call at any time."""

    @abstractmethod
    def cleanup(self, handle: RunHandle) -> None:
        """Remove what the run left behind: containers, volumes and other objects. Best effort, and it does
        nothing to a run started with `keep`."""

    @abstractmethod
    def list_runs(self, labels: Mapping[str, str] | None = None) -> list[RunInfo]:
        """The runs that carry every label in `labels`, running or not; all runs when it is None."""

    def inspect_run(self, run_id: str) -> RunInfo | None:
        """The run whose `ssebench.run-id` label is `run_id`, or None."""
        found = self.list_runs({RUN_ID_LABEL: run_id})
        return found[0] if found else None

    def endpoint(self, handle: RunHandle, port: int) -> str:
        """A URL, `http://host:port`, at which this process can reach `port` of the run's container.

        A tool that watches a run, such as the web UI, reaches the daemon (4263) and the OpenCode server
        (4096) of a running container through it. The URL has to work from the machine that calls this,
        wherever the containers are: a container address where that is routable, a published or forwarded
        port, or a Service. It must stay valid after this process exits, since the caller is often a
        short-lived command: a backend that needs a port-forward keeps one running and reuses it on the
        next call. It carries no credentials.

        Raises:
            BackendError: If the run is not running, or this backend cannot reach its ports.
        """
        raise BackendError(f"The {self.name} backend cannot reach the ports of a run")

    def exec_argv(
        self,
        handle: RunHandle,
        command: Sequence[str],
        *,
        user: str | None = None,
        workdir: str | None = None,
        tty: bool = False,
        stdin: bool = False,
        env_names: Sequence[str] = (),
    ) -> list[str]:
        """The argument vector of a local command that runs `command` in the run's container.

        The caller executes it with the standard streams attached; nothing goes through a shell, and
        `command` reaches the container as separate arguments. `tty` allocates a terminal, `stdin` keeps
        standard input open, and `env_names` are variables that the container's process gets with the
        values they have in the caller's environment. Their values never appear in the vector, since a
        process list shows it: a backend that cannot pass them otherwise raises. Set `supports_exec` on a
        backend that implements this.

        Raises:
            BackendError: If the run cannot run commands, for example because it is not running.
        """
        raise BackendError(f"The {self.name} backend cannot run commands in a run")


def describe_command(command: list[str]) -> str:
    """The first words of a command, for an error message; the rest can hold a secret."""
    return shlex.join(command[:3])
