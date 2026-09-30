import logging
import shutil
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, final, override

from ssebench.agents import Agent
from ssebench.backends import (
    AGENT_LABEL,
    ARCHIVE_PATH,
    MODEL_LABEL,
    RESULTS_LABEL,
    RESULTS_PATH,
    RUN_ID_LABEL,
    TASK_LABEL,
    WEBUI_LABEL,
    Backend,
    BackendError,
    Egress,
    ImageRequest,
    Images,
    Mode,
    Mount,
    NetworkPolicy,
    RunSpec,
    SidecarPair,
)
from ssebench.errors import UserError
from ssebench.extensions import DEFAULT_BACKEND, DEFAULT_TOOL_LAYER, get_backend, get_tool_layer
from ssebench.models import Model, NoModel
from ssebench.runner.layout import SUMMARY_FILE, mark_latest, new_run_id, run_dir
from ssebench.runner.lifecycle import execute
from ssebench.runner.plugin_report import read_plugin_report
from ssebench.runner.reference import (
    is_reference_run,
    reference_artifacts,
    reference_patch,
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

ARCHIVE_DIR = "archive"
REFERENCE_PATCH_FILE = "reference.patch"

# What a stopped container ends with: 128 plus SIGTERM, or plus SIGKILL, which follows the grace period.
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

    A kept container waits to be stopped once the evaluator has written the grade, so that stop
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
    per_task_result.plugin_results = read_plugin_report(evaluator_file.parent / ARCHIVE_DIR)
    replace_file(evaluator_file.with_name(SUMMARY_FILE), per_task_result.model_dump_json())


class BenchmarkRunner(ABC):
    """One run of an agent on a task: it prepares the images, describes the run to a backend and records the results.

    The runner knows what a run is and never touches a container platform; the `Backend` does.
    `prebuilt` uses the published agent images of the run instead of building its layers.
    """

    mode: ClassVar[Mode]
    running_message: ClassVar[str]

    def __init__(
        self,
        model: Model | NoModel,
        agent: Agent,
        task: Task,
        timeout: int,
        difficulty: int,
        keep_container: bool = False,
        egress: Egress = "restricted",
        run_id: str | None = None,
        backend: Backend | None = None,
        prebuilt: bool = False,
    ):
        self.model = model
        self.agent = agent
        self.task = task
        self.timeout = timeout
        self.difficulty = difficulty
        self.keep_container = keep_container
        self.egress: Egress = egress
        self.run_id = run_id or new_run_id()
        self.backend = backend or get_backend(DEFAULT_BACKEND)
        self.prebuilt = prebuilt
        self.images: Images | None = None

    def build(self):
        """Make the images of the run available: build the layers, or with `prebuilt` pull the published ones."""
        if not self.prebuilt and not self.backend.builds_images:
            raise UserError(f"The {self.backend.name} backend cannot build images; use prebuilt images")
        self.images = self.backend.prepare_images(self.image_request())

    @abstractmethod
    def image_request(self) -> ImageRequest: ...

    @abstractmethod
    def run_spec(self, results_path: Path, reference: Path | None) -> RunSpec: ...

    @abstractmethod
    def _run_config(self) -> RunConfig: ...

    @abstractmethod
    def _report_exit(self, status: int, evaluator_file: Path) -> None: ...

    def _labels(self, results_path: Path) -> dict[str, str]:
        return {
            RESULTS_LABEL: str(results_path),
            WEBUI_LABEL: "true",
            TASK_LABEL: self.task.name,
            MODEL_LABEL: self.model.model_name,
            AGENT_LABEL: self.agent.agent_name,
            **reference_run_labels(self.agent.agent_name),
            RUN_ID_LABEL: self.run_id,
        }

    def _mounts(self, results_path: Path) -> tuple[Mount, Mount]:
        return (
            Mount(source=str(results_path), target=RESULTS_PATH),
            Mount(source=str(results_path / ARCHIVE_DIR), target=ARCHIVE_PATH),
        )

    def run(self):
        assert self.images is not None

        started_at = datetime.now(UTC)
        results_path = run_dir(self.task.name, self.agent.agent_name, self.model.model_name, self.run_id).absolute()
        evaluator_file = prepare_run_directory(results_path)
        mark_latest(results_path)

        # A prebuilt run has no case image; the image it runs holds the same task files.
        source_image = self.images.task_image() if self.prebuilt else None
        with reference_patch(self.backend, self.agent.agent_name, self.task, source_image) as patch:
            spec = self.run_spec(results_path, patch)
            logger.info(f"{self.running_message}: {self.task.name}")
            try:
                status = execute(self.backend, spec, results_path)
            except BackendError as e:
                logger.error(f"{self.mode.capitalize()} run failed: {e}")
            else:
                self._report_exit(status, evaluator_file)
        save_reference_patch(self.task, results_path)

        record_results(self.task, self._run_config(), self.model.get_spend(), evaluator_file, self.run_id, started_at)


@final
class BenchmarkSandboxRunner(BenchmarkRunner):
    mode = "sandbox"
    running_message = "Running Benchmark"

    def __init__(
        self,
        model: Model | NoModel,
        agent: Agent,
        task: Task,
        timeout: int,
        difficulty: int,
        keep_container: bool = False,
        tool_layer: str = DEFAULT_TOOL_LAYER,
        egress: Egress = "restricted",
        plugins: list[str] | None = None,
        select_plugins: bool = False,
        run_id: str | None = None,
        backend: Backend | None = None,
        prebuilt: bool = False,
    ):
        super().__init__(model, agent, task, timeout, difficulty, keep_container, egress, run_id, backend, prebuilt)
        if prebuilt and (tool_layer != DEFAULT_TOOL_LAYER or select_plugins):
            raise UserError(
                "Prebuilt images come with their tool layer and plugins; --tool-layer and --plugin need a build"
            )
        self.tool_layer_name = tool_layer
        self.tool_layer = get_tool_layer(tool_layer)
        # plugins: the names to install and enable for the run.
        # select_plugins is True when the user chose them with --plugin, so the
        # container is told exactly which to run (SSE_PLUGINS); when False the
        # set came from plugins.yaml's enabled field and the container reads the
        # same file.
        self.plugins = plugins or []
        self.select_plugins = select_plugins

    @override
    def image_request(self) -> ImageRequest:
        return ImageRequest(
            mode="sandbox",
            task=self.task,
            agent=self.agent,
            tool_layer=self.tool_layer,
            plugins=tuple(self.plugins),
            prebuilt=self.prebuilt,
        )

    @override
    def run_spec(self, results_path: Path, reference: Path | None) -> RunSpec:
        assert self.images is not None
        results, archive = self._mounts(results_path)
        return RunSpec(
            run_id=self.run_id,
            mode="sandbox",
            task_name=self.task.name,
            image=self.images.agent,
            env={
                "SSE_API_KEY": self.model.api_key,
                "SSE_BASE_URL": self.model.service_url,
                "SSE_MODEL_NAME": self.model.model_name,
                "SSE_ARCHIVE": ARCHIVE_PATH,
                "SSE_DIFFICULTY": str(self.difficulty),
                "TIMEOUT": str(self.timeout),
                "SSE_KEEP_ALIVE": "1" if self.keep_container else "0",
                **({"SSE_PLUGINS": ",".join(self.plugins)} if self.select_plugins else {}),
            },
            results=results,
            archive=archive,
            artifacts=reference_artifacts(self.agent.agent_name, reference),
            network=NetworkPolicy(egress=self.egress),
            platform=self.task.platform,
            labels=self._labels(results_path),
            timeout=self.timeout,
            keep=self.keep_container,
        )

    @override
    def _report_exit(self, status: int, evaluator_file: Path) -> None:
        if status == 0:
            return
        if stopped_after_grading(status, self.keep_container, evaluator_file):
            logger.info(f"The kept container was stopped after grading (exit status {status})")
        else:
            logger.error(f"Agent container stopped with a non-zero exit status: {status}")

    @override
    def _run_config(self) -> RunConfig:
        return RunConfig(
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


@final
class BenchmarkSidecarRunner(BenchmarkRunner):
    mode = "sidecar"
    running_message = "Running agent"

    @override
    def image_request(self) -> ImageRequest:
        return ImageRequest(mode="sidecar", task=self.task, agent=self.agent, tool_layer=None, prebuilt=self.prebuilt)

    @override
    def run_spec(self, results_path: Path, reference: Path | None) -> RunSpec:
        assert self.images is not None and self.images.environment is not None
        results, archive = self._mounts(results_path)
        return RunSpec(
            run_id=self.run_id,
            mode="sidecar",
            task_name=self.task.name,
            image=self.images.agent,
            env={
                "SSE_API_KEY": self.model.api_key,
                "SSE_BASE_URL": self.model.service_url,
                "SSE_MODEL_NAME": self.model.model_name,
                "TIMEOUT": str(self.timeout),
            },
            results=results,
            archive=archive,
            artifacts=reference_artifacts(self.agent.agent_name, reference),
            network=NetworkPolicy(egress=self.egress),
            platform=self.task.platform,
            labels=self._labels(results_path),
            timeout=self.timeout,
            keep=self.keep_container,
            sidecar=SidecarPair(
                task_name=self.task.name,
                source_dir=self.task.get_task_metadata().source,
                environment_image=self.images.environment,
                difficulty=self.difficulty,
                keep_alive=self.keep_container,
            ),
        )

    @override
    def _report_exit(self, status: int, evaluator_file: Path) -> None:
        if status != 0:
            logger.error(f"Sidecar run failed: `docker run` exited with status {status}")

    @override
    def _run_config(self) -> RunConfig:
        return RunConfig(
            agent=self.agent.agent_name,
            model=self.model.model_name,
            mode="sidecar",
            timeout=self.timeout,
            difficulty=self.difficulty,
            egress="open" if self.egress == "open" else "restricted",
            reference_run=is_reference_run(self.agent.agent_name),
        )
