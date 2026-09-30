import logging
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import final, override
from uuid import uuid4

from ssebench import stack
from ssebench.agents import Agent
from ssebench.arch import platform_args
from ssebench.errors import UserError
from ssebench.extensions import DEFAULT_TOOL_LAYER, get_tool_layer
from ssebench.middleware import (
    SidecarToolLayerAgentRuntime,
    SidecarToolLayerEnvironment,
    ToolLayerContext,
)
from ssebench.models import Model, NoModel
from ssebench.pipe import build_pipe
from ssebench.runner.layout import SUMMARY_FILE, mark_latest, new_run_id, run_dir
from ssebench.runner.lifecycle import run_container, run_id_labels
from ssebench.runner.reference import (
    is_reference_run,
    reference_patch,
    reference_patch_mount,
    reference_run_labels,
)
from ssebench.runner.result import (
    EvaluationResult,
    FrameworkResult,
    PatchResult,
    PerTaskEvaluationResult,
    RunConfig,
    RuntimeResult,
)
from ssebench.tasks import Task

logger = logging.getLogger(__name__)

ARCHIVE_PATH = "/tmp/sse-archive"
"""Where a task container has the agent's archive (`SSE_ARCHIVE`): the run directory's `archive/`."""
ARCHIVE_DIR = "archive"
RESULTS_PATH = "/var/lib/ssebench/results"
"""Where a task container has the run directory: root-only, for the grade, the graded patch and the logs."""
REFERENCE_PATCH_FILE = "reference.patch"
RESULTS_LABEL = "ssebench.results"
"""Container label with the run's own directory on the host, for the web UI."""

# What `docker stop` ends a container with: 128 plus SIGTERM, or plus SIGKILL, which follows
# the ten seconds it allows.
STOP_STATUSES = (143, 137)


def prepare_run_directory(results_path: Path) -> Path:
    """Create the run directory with its agent archive, and return the path of its `result.json`.

    Raises:
        UserError: If the directory exists, since a run never adds to another run's results.
    """
    results_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        results_path.mkdir()
    except FileExistsError:
        raise UserError(f"{results_path} already has results; give the run another --run-id") from None
    (results_path / ARCHIVE_DIR).mkdir()
    evaluator_file = results_path / "result.json"
    evaluator_file.touch()
    return evaluator_file


def save_reference_patch(task: Task, results_path: Path) -> None:
    """Copy the task's reference patch into the run directory after the run, for reports and the web UI.

    The daemon serves it only on its admin socket, so this is how tools on the host get it.
    """
    patch = task.get_task_metadata().files.patch
    source = task.task_file(patch) if patch is not None else None
    if source is None:
        logger.debug(f"No local copy of the reference patch of {task.name}")
        return
    _ = shutil.copyfile(source, results_path / REFERENCE_PATCH_FILE)


def replace_file(path: Path, content: str) -> None:
    """Replace `path` in one step. The container's root wrote it, so it cannot be rewritten in place."""
    tmp = path.with_name(f".{path.name}.tmp")
    _ = tmp.write_text(content)
    _ = tmp.replace(path)


def stopped_after_grading(returncode: int, keep_container: bool, evaluator_file: Path) -> bool:
    """Whether a container that exited with `returncode` was stopped after grading, as a kept one is.

    A kept container waits for `docker stop` once the evaluator has written the grade, so that stop
    is how the run ends. The same status before the grade exists is a failed run.
    """
    return keep_container and returncode in STOP_STATUSES and evaluator_file.stat().st_size > 0


def record_results(
    task: Task,
    run_config: RunConfig,
    spend: float,
    evaluator_file: Path,
    run_id: str | None = None,
    started_at: datetime | None = None,
) -> None:
    """Complete the run's result.json with the run settings, and write the summary beside it."""
    content = evaluator_file.read_text().strip()
    if content:
        container_result = EvaluationResult.model_validate_json(content)
    else:
        logger.error("Evaluator produced no output; recording framework failure.")
        container_result = EvaluationResult(
            patch_result=PatchResult(error_msg="No result: evaluator did not produce output"),
            runtime_result=RuntimeResult(agent_duration=0, agent_timeout=False, evaluator_timeout=False),
        )
    container_result.config = run_config
    replace_file(evaluator_file, container_result.model_dump_json())

    per_task_result = PerTaskEvaluationResult.build(
        tm=task.get_task_metadata(),
        rc=run_config,
        frs=FrameworkResult(spend=spend),
        crs=container_result,
        run_id=run_id,
        started_at=started_at,
    )
    replace_file(evaluator_file.with_name(SUMMARY_FILE), per_task_result.model_dump_json())


class BenchmarkRunner(ABC):
    @abstractmethod
    def __init__(
        self,
        model: Model | NoModel,
        agent: Agent,
        task: Task,
        timeout: int,
        difficulty: int,
        keep_container: bool = False,
        egress: str = "restricted",
        run_id: str | None = None,
    ): ...

    @abstractmethod
    def build(self): ...

    @abstractmethod
    def run(self): ...


@final
class BenchmarkSandboxRunner(BenchmarkRunner):
    def __init__(
        self,
        model: Model | NoModel,
        agent: Agent,
        task: Task,
        timeout: int,
        difficulty: int,
        keep_container: bool = False,
        tool_layer: str = DEFAULT_TOOL_LAYER,
        egress: str = "restricted",
        plugins: list[str] | None = None,
        select_plugins: bool = False,
        run_id: str | None = None,
    ):
        self.model = model
        self.run_id = run_id or new_run_id()
        self.agent = agent
        self.task = task
        self.timeout = timeout
        self.difficulty = difficulty
        self.keep_container = keep_container
        self.tool_layer_name = tool_layer
        self.tool_layer = get_tool_layer(tool_layer)
        self.egress = egress
        # plugins: the names to install and enable for the run.
        # select_plugins is True when the user chose them with --plugin, so the
        # container is told exactly which to run (SSE_PLUGINS); when False the
        # set came from plugins.yaml's enabled field and the container reads the
        # same file.
        self.plugins = plugins or []
        self.select_plugins = select_plugins

        self.sandbox_image = None

    @override
    def build(self):
        metadata = self.task.get_task_metadata()
        tool_layer = self.tool_layer(
            ToolLayerContext(
                task_name=self.task.name,
                source_dir=metadata.source,
                plugins=tuple(self.plugins),
                platform=self.task.platform,
            )
        )
        self.sandbox_image = build_pipe([self.task, tool_layer, self.agent])
        logger.info(f"Build benchmark image {self.sandbox_image}")

    def docker_command(self, results_path: Path, reference_patch: Path | None = None) -> list[str]:
        """The `docker run` command of the task container.

        `reference_patch` reaches the container only when the agent is the reference agent.
        """
        assert self.sandbox_image is not None
        docker_cmd = ["docker", "run"]
        if not self.keep_container:
            docker_cmd.append("--rm")
        docker_cmd.extend(
            [
                *platform_args(self.task.platform),
                "--network",
                stack.run_network(self.egress),
                "-e",
                f"SSE_API_KEY={self.model.api_key}",
                "-e",
                f"SSE_BASE_URL={self.model.service_url}",
                "-e",
                f"SSE_MODEL_NAME={self.model.model_name}",
                "-e",
                f"SSE_ARCHIVE={ARCHIVE_PATH}",
                "-e",
                f"SSE_DIFFICULTY={self.difficulty}",
                "-e",
                f"TIMEOUT={self.timeout}",
                "-e",
                f"SSE_KEEP_ALIVE={'1' if self.keep_container else '0'}",
                *(["-e", f"SSE_PLUGINS={','.join(self.plugins)}"] if self.select_plugins else []),
                "-v",
                f"{results_path}:{RESULTS_PATH}",
                "-v",
                f"{results_path / ARCHIVE_DIR}:{ARCHIVE_PATH}",
                *reference_patch_mount(self.agent.agent_name, reference_patch),
                "--label",
                f"{RESULTS_LABEL}={results_path}",
                "--label",
                "ssebench.webui=true",
                "--label",
                f"ssebench.task-id={self.task.name}",
                "--label",
                f"ssebench.model={self.model.model_name}",
                "--label",
                f"ssebench.agent={self.agent.agent_name}",
                *reference_run_labels(self.agent.agent_name),
                *run_id_labels(self.run_id),
                self.sandbox_image,
            ]
        )
        return docker_cmd

    @override
    def run(self):
        assert self.sandbox_image is not None

        started_at = datetime.now(UTC)
        results_path = run_dir(self.task.name, self.agent.agent_name, self.model.model_name, self.run_id).absolute()
        evaluator_file = prepare_run_directory(results_path)
        mark_latest(results_path)

        with reference_patch(self.agent.agent_name, self.task) as patch:
            try:
                logger.info(f"Running Benchmark: {self.task.name}")
                run_container(self.docker_command(results_path, patch))
            except subprocess.CalledProcessError as e:
                if stopped_after_grading(e.returncode, self.keep_container, evaluator_file):
                    logger.info(f"The kept container was stopped after grading (exit status {e.returncode})")
                else:
                    # The exception's text is the docker command line, which carries the run's proxy key.
                    logger.error(f"Agent container stopped with a non-zero exit status: {e.returncode}")
        save_reference_patch(self.task, results_path)

        run_config = RunConfig(
            agent=self.agent.agent_name,
            model=self.model.model_name,
            mode="sandbox",
            timeout=self.timeout,
            difficulty=self.difficulty,
            tool_layer=self.tool_layer_name,
            egress="open" if self.egress == "open" else "restricted",
            reference_run=is_reference_run(self.agent.agent_name),
            plugins=self.plugins,
        )
        record_results(self.task, run_config, self.model.get_spend(), evaluator_file, self.run_id, started_at)


SIDECAR_SOCKET_DIR = "/run/ssebench"
"""Where both containers of a sidecar run mount the volume that holds the daemon's sockets."""
SIDECAR_DAEMON_SOCKET = f"{SIDECAR_SOCKET_DIR}/sse.sock"


def _docker(*args: str) -> None:
    _ = subprocess.run(["docker", *args], check=True, stdout=subprocess.DEVNULL)


@dataclass(frozen=True, kw_only=True)
class SidecarPair:
    """The two containers of a sidecar run and the volumes they share.

    The environment container is the case image with the daemon; the agent container is the
    runtime image with the agent, the MCP server and the evaluator. They share the project's source
    tree, the results directory and a root-owned directory with the daemon's sockets. The task's
    `/ssebench` (reference patch, hidden tests, scripts) stays in the environment container.
    """

    task_name: str
    source_dir: str
    """Absolute path of the project source, the same in both containers."""
    results: str
    """What to mount at the results path, root-only, in both containers: a host directory or a volume name."""
    archive: str
    """What to mount at the archive path, the agent's, in both containers: a host directory or a volume name."""
    network: str
    difficulty: int
    keep_alive: bool = False
    run_id: str = field(default_factory=lambda: uuid4().hex[:12])
    platform: str | None = None
    """The `linux/<arch>` platform of both containers, that of their images; None runs the Docker host's own."""

    @property
    def environment_name(self) -> str:
        return f"ssebench-env-{self.task_name.lower()}-{self.run_id}"

    @property
    def source_volume(self) -> str:
        return f"ssebench-{self.run_id}-source"

    @property
    def socket_volume(self) -> str:
        return f"ssebench-{self.run_id}-sockets"

    def create_volumes(self) -> None:
        for volume in (self.source_volume, self.socket_volume):
            _docker("volume", "create", "--label", f"ssebench.run={self.run_id}", volume)

    def _shared_options(self) -> list[str]:
        return [
            *platform_args(self.platform),
            "--network",
            self.network,
            "--label",
            f"ssebench.run={self.run_id}",
            "-e",
            f"SSE_ARCHIVE={ARCHIVE_PATH}",
            "-e",
            f"SSE_DAEMON_SOCKET={SIDECAR_DAEMON_SOCKET}",
            # The daemon enforces the difficulty gate; the agent container's MCP server mirrors it.
            "-e",
            f"SSE_DIFFICULTY={self.difficulty}",
            "-v",
            f"{self.archive}:{ARCHIVE_PATH}",
            "-v",
            f"{self.source_volume}:{self.source_dir}",
            "-v",
            f"{self.socket_volume}:{SIDECAR_SOCKET_DIR}",
            "-v",
            f"{self.results}:{RESULTS_PATH}",
            "-e",
            f"SSE_RESULTS={RESULTS_PATH}",
        ]

    def environment_options(self) -> list[str]:
        """`docker run` options of the environment container, before its image."""
        return [
            "--name",
            self.environment_name,
            *self._shared_options(),
            "-e",
            f"SSE_KEEP_ALIVE={'1' if self.keep_alive else '0'}",
        ]

    def agent_options(self, env: dict[str, str] | None = None) -> list[str]:
        """`docker run` options of the agent container, before its image.

        The evaluator writes the grade to `result.json` in the run directory.
        """
        options = self._shared_options()
        for name, value in (env or {}).items():
            options += ["-e", f"{name}={value}"]
        return options

    def remove(self) -> None:
        """Remove the environment container and the volumes; best effort."""
        for cmd in (
            ["docker", "rm", "--force", self.environment_name],
            ["docker", "volume", "rm", self.source_volume, self.socket_volume],
        ):
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.warning(f"Failed to clean up: {result.stderr.strip()}")


@final
class BenchmarkSidecarRunner(BenchmarkRunner):
    def __init__(
        self,
        model: Model | NoModel,
        agent: Agent,
        task: Task,
        timeout: int,
        difficulty: int,
        keep_container: bool = False,
        egress: str = "restricted",
        run_id: str | None = None,
    ):
        self.model = model
        self.agent = agent
        self.task = task
        self.timeout = timeout
        self.difficulty = difficulty
        self.keep_container = keep_container
        self.egress = egress
        self.run_id = run_id or new_run_id()

        self.sidecar_agentrt_image: str | None = None
        self.sidecar_environ_image: str | None = None

    @override
    def build(self):
        context = ToolLayerContext(
            task_name=self.task.name, source_dir=self.task.get_task_metadata().source, platform=self.task.platform
        )

        tool_layer_agentrt = SidecarToolLayerAgentRuntime(context)
        self.sidecar_agentrt_image = build_pipe([tool_layer_agentrt, self.agent])
        logger.info(f"Built agent image {self.sidecar_agentrt_image}")

        tool_layer_environ = SidecarToolLayerEnvironment(context)
        self.sidecar_environ_image = build_pipe([self.task, tool_layer_environ])
        logger.info(f"Built environment image {self.sidecar_environ_image}")

    @override
    def run(self):
        assert self.sidecar_agentrt_image is not None
        assert self.sidecar_environ_image is not None

        started_at = datetime.now(UTC)
        results_path = run_dir(self.task.name, self.agent.agent_name, self.model.model_name, self.run_id).absolute()
        evaluator_file = prepare_run_directory(results_path)
        mark_latest(results_path)

        pair = SidecarPair(
            task_name=self.task.name,
            source_dir=self.task.get_task_metadata().source,
            results=str(results_path),
            archive=str(results_path / ARCHIVE_DIR),
            network=stack.run_network(self.egress),
            difficulty=self.difficulty,
            keep_alive=self.keep_container,
            platform=self.task.platform,
        )
        labels = [
            "--label",
            "ssebench.webui=true",
            "--label",
            f"ssebench.task-id={self.task.name}",
            "--label",
            f"ssebench.model={self.model.model_name}",
            "--label",
            f"ssebench.agent={self.agent.agent_name}",
            *reference_run_labels(self.agent.agent_name),
            "--label",
            f"{RESULTS_LABEL}={results_path}",
            *run_id_labels(self.run_id),
        ]

        try:
            pair.create_volumes()
            # The empty source volume takes the project from the environment image, so that
            # container starts first; the agent container's entrypoint waits for the daemon.
            logger.info(f"Starting environment {pair.environment_name} (run {pair.run_id})")
            _docker("run", "--detach", *pair.environment_options(), *labels, self.sidecar_environ_image)

            with reference_patch(self.agent.agent_name, self.task) as patch:
                logger.info(f"Running agent: {self.task.name}")
                docker_cmd = ["docker", "run"]
                if not self.keep_container:
                    docker_cmd.append("--rm")
                docker_cmd += pair.agent_options(
                    {
                        "SSE_API_KEY": self.model.api_key,
                        "SSE_BASE_URL": self.model.service_url,
                        "SSE_MODEL_NAME": self.model.model_name,
                        "TIMEOUT": str(self.timeout),
                    },
                )
                docker_cmd += [*reference_patch_mount(self.agent.agent_name, patch), self.sidecar_agentrt_image]
                run_container(docker_cmd)
        except subprocess.CalledProcessError as e:
            # The exception's text is the docker command line, which carries the run's proxy key.
            logger.error(f"Sidecar run failed: `docker run` exited with status {e.returncode}")
        finally:
            if self.keep_container:
                logger.info(f"Kept the containers and volumes labelled ssebench.run={pair.run_id}")
            else:
                pair.remove()
        save_reference_patch(self.task, results_path)

        run_config = RunConfig(
            agent=self.agent.agent_name,
            model=self.model.model_name,
            mode="sidecar",
            timeout=self.timeout,
            difficulty=self.difficulty,
            egress="open" if self.egress == "open" else "restricted",
            reference_run=is_reference_run(self.agent.agent_name),
        )
        record_results(self.task, run_config, self.model.get_spend(), evaluator_file, self.run_id, started_at)
