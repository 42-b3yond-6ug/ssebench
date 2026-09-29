import logging
import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import final, override
from uuid import uuid4

from ssebench.agents import Agent
from ssebench.extensions import DEFAULT_TOOL_LAYER, get_tool_layer
from ssebench.middleware import (
    SidecarToolLayerAgentRuntime,
    SidecarToolLayerEnvironment,
    ToolLayerContext,
)
from ssebench.models import Model
from ssebench.pipe import build_pipe
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


def clear_directory(path: Path) -> None:
    """Clear all contents of a directory without removing the directory itself."""
    if not path.exists():
        return
    for item in path.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    logger.debug(f"Cleared contents of {path}")


class BenchmarkRunner(ABC):
    @abstractmethod
    def __init__(
        self, model: Model, agent: Agent, task: Task, timeout: int, difficulty: int, keep_container: bool = False
    ): ...

    @abstractmethod
    def build(self): ...

    @abstractmethod
    def run(self): ...


@final
class BenchmarkSandboxRunner(BenchmarkRunner):
    def __init__(
        self,
        model: Model,
        agent: Agent,
        task: Task,
        timeout: int,
        difficulty: int,
        keep_container: bool = False,
        tool_layer: str = DEFAULT_TOOL_LAYER,
    ):
        self.model = model
        self.agent = agent
        self.task = task
        self.timeout = timeout
        self.difficulty = difficulty
        self.keep_container = keep_container
        self.tool_layer_name = tool_layer
        self.tool_layer = get_tool_layer(tool_layer)

        self.sandbox_image = None

    @override
    def build(self):
        metadata = self.task.get_task_metadata()
        tool_layer = self.tool_layer(ToolLayerContext(task_name=self.task.name, source_dir=metadata.source))
        self.sandbox_image = build_pipe([self.task, tool_layer, self.agent])
        logger.info(f"Build benchmark image {self.sandbox_image}")

    @override
    def run(self):
        assert self.sandbox_image is not None

        results_path = (Path("results") / self.task.name / self.model.model_name / self.agent.agent_name).absolute()
        os.makedirs(results_path, exist_ok=True)
        clear_directory(results_path)

        evaluator_file = results_path / "result.json"
        evaluator_file.touch(exist_ok=True)

        try:
            logger.info(f"Running Benchmark: {self.task.name}")
            docker_cmd = ["docker", "run"]
            if not self.keep_container:
                docker_cmd.append("--rm")
            docker_cmd.extend(
                [
                    "--network",
                    "ssebench_net",
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
                    "-v",
                    f"{evaluator_file}:/sse_result",
                    "-v",
                    f"{results_path}:{ARCHIVE_PATH}",
                    "--label",
                    "ssebench.webui=true",
                    "--label",
                    f"ssebench.task-id={self.task.name}",
                    "--label",
                    f"ssebench.model={self.model.model_name}",
                    "--label",
                    f"ssebench.agent={self.agent.agent_name}",
                    self.sandbox_image,
                ]
            )
            _ = subprocess.run(docker_cmd, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Agent container stopped with a non-zero exit: {e}")

        content = evaluator_file.read_text().strip()
        if content:
            container_result = EvaluationResult.model_validate_json(content)
        else:
            logger.error("Evaluator produced no output; recording framework failure.")
            container_result = EvaluationResult(
                patch_result=PatchResult(error_msg="No result: evaluator did not produce output"),
                runtime_result=RuntimeResult(agent_duration=0, agent_timeout=False, evaluator_timeout=False),
            )

        framework_result = FrameworkResult(spend=self.model.get_spend())

        run_config = RunConfig(
            agent=self.agent.agent_name,
            model=self.model.model_name,
            mode="sandbox",
            timeout=self.timeout,
            difficulty=self.difficulty,
            tool_layer=self.tool_layer_name,
        )

        per_task_result = PerTaskEvaluationResult.build(
            tm=self.task.get_task_metadata(),
            rc=run_config,
            frs=framework_result,
            crs=container_result,
        )

        result_folder = Path("results")
        result_folder.mkdir(exist_ok=True)
        result_json_path = result_folder / f"{self.task.name}-{self.agent.agent_name}-{self.model.model_name}.json"

        report_json_str = per_task_result.model_dump_json()
        with open(result_json_path, "w") as f:
            _ = f.write(report_json_str)


@final
class BenchmarkSidecarRuner(BenchmarkRunner):
    def __init__(
        self,
        model: Model,
        agent: Agent,
        task: Task,
        timeout: int,
        difficulty: int,
        keep_container: bool = False,
    ):
        self.model = model
        self.agent = agent
        self.task = task
        self.timeout = timeout
        self.difficulty = difficulty
        self.keep_container = keep_container

        self.sidecar_agentrt_image: str | None = None
        self.sidecar_environ_image: str | None = None

    @override
    def build(self):
        context = ToolLayerContext(task_name=self.task.name, source_dir=self.task.get_task_metadata().source)

        tool_layer_agentrt = SidecarToolLayerAgentRuntime(context)
        self.sidecar_agentrt_image = build_pipe([tool_layer_agentrt, self.agent])
        logger.info(f"[experimental] Build agent runtime image {self.sidecar_agentrt_image}")

        tool_layer_environ = SidecarToolLayerEnvironment(context)
        self.sidecar_environ_image = build_pipe([self.task, tool_layer_environ])
        logger.info(f"[experimental] Build environment image {self.sidecar_environ_image}")

    @override
    def run(self):
        assert self.sidecar_agentrt_image is not None
        assert self.sidecar_environ_image is not None

        results_path = (Path("results") / self.task.name / self.model.model_name / self.agent.agent_name).absolute()
        os.makedirs(results_path, exist_ok=True)
        clear_directory(results_path)

        # source_volume_name: mounted at the task's source path inside both containers
        source_volume_name = uuid4().hex
        try:
            _ = subprocess.run(
                [
                    "docker",
                    "volume",
                    "create",
                    source_volume_name,
                ],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Docker volume creation failed: {e}")

        # scripts_volume_name: mounted at /ssebench, contains build/test scripts from the case image
        scripts_volume_name = uuid4().hex
        try:
            _ = subprocess.run(
                [
                    "docker",
                    "volume",
                    "create",
                    scripts_volume_name,
                ],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Docker volume creation failed: {e}")

        source = Path(self.task.get_task_metadata().source).resolve()
        environment_name = f"env-{self.task.get_task_metadata().id}"

        # Start the environment first
        # Environment must map the source code to an empty docker volume
        try:
            # TODO: if we want to map parent of source?
            logger.info(f"Starting Environment: {self.task.name}")
            _ = subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--name",
                    environment_name,
                    "-e",
                    f"SSE_ARCHIVE={ARCHIVE_PATH}",
                    "-e",
                    f"SSE_DAEMON_SOCKET={ARCHIVE_PATH}/please-work.sock",
                    "-e",
                    f"SSE_KEEP_ALIVE={'1' if self.keep_container else '0'}",
                    "-v",
                    f"{results_path}:{ARCHIVE_PATH}",
                    "-v",
                    f"{source_volume_name}:{source}",
                    "-v",
                    f"{scripts_volume_name}:/ssebench",
                    "--label",
                    "ssebench.webui=true",
                    "--label",
                    f"ssebench.task-id={self.task.name}",
                    "--label",
                    f"ssebench.model={self.model.model_name}",
                    "--label",
                    f"ssebench.agent={self.agent.agent_name}",
                    self.sidecar_environ_image,
                ],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"Environment started failed: {e}")

        evaluator_file = results_path / "result.json"
        evaluator_file.touch(exist_ok=True)

        try:
            logger.info(f"Running Agent: {self.task.name}")
            docker_cmd = ["docker", "run"]
            if not self.keep_container:
                docker_cmd.append("--rm")
            docker_cmd.extend(
                [
                    "--network",
                    "ssebench_net",
                    "-e",
                    f"SSE_API_KEY={self.model.api_key}",
                    "-e",
                    f"SSE_BASE_URL={self.model.service_url}",
                    "-e",
                    f"SSE_MODEL_NAME={self.model.model_name}",
                    "-e",
                    f"SSE_ARCHIVE={ARCHIVE_PATH}",
                    "-e",
                    f"SSE_DAEMON_SOCKET={ARCHIVE_PATH}/please-work.sock",
                    "-e",
                    f"SSE_DIFFICULTY={self.difficulty}",
                    "-e",
                    f"TIMEOUT={self.timeout}",
                    "-v",
                    f"{evaluator_file}:/sse_result",
                    "-v",
                    f"{results_path}:{ARCHIVE_PATH}",
                    "-v",
                    f"{source_volume_name}:{source}",
                    "-v",
                    f"{scripts_volume_name}:/ssebench",
                    self.sidecar_agentrt_image,
                ]
            )
            _ = subprocess.run(docker_cmd, check=True)
        except subprocess.CalledProcessError as e:
            logger.warning(f"Agent runtime stopped with a non-zero exit: {e}")

        # stop the environment, and clean the volume (skip if keeping containers)
        if not self.keep_container:
            try:
                _ = subprocess.run(["docker", "kill", environment_name], check=True)
                _ = subprocess.run(["docker", "rm", environment_name], check=True)
                _ = subprocess.run(["docker", "volume", "rm", source_volume_name], check=True)
                _ = subprocess.run(["docker", "volume", "rm", scripts_volume_name], check=True)
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to clean up: {e}")

        # Collect results
        framework_result = FrameworkResult(spend=self.model.get_spend())

        content = evaluator_file.read_text().strip()
        if content:
            container_result = EvaluationResult.model_validate_json(content)
        else:
            logger.error("Evaluator produced no output; recording framework failure.")
            container_result = EvaluationResult(
                patch_result=PatchResult(error_msg="No result: evaluator did not produce output"),
                runtime_result=RuntimeResult(agent_duration=0, agent_timeout=False, evaluator_timeout=False),
            )

        run_config = RunConfig(
            agent=self.agent.agent_name,
            model=self.model.model_name,
            mode="sidecar",
            timeout=self.timeout,
            difficulty=self.difficulty,
        )

        per_task_result = PerTaskEvaluationResult.build(
            tm=self.task.get_task_metadata(),
            rc=run_config,
            frs=framework_result,
            crs=container_result,
        )

        result_folder = Path("results")
        result_folder.mkdir(exist_ok=True)
        result_json_path = result_folder / f"{self.task.name}-{self.agent.agent_name}-{self.model.model_name}.json"

        report_json_str = per_task_result.model_dump_json()
        with open(result_json_path, "w") as f:
            _ = f.write(report_json_str)
