"""The Docker backend: a run is one or two containers on the local Docker daemon.

The task container runs in the foreground of a `docker run` process, so its output reaches this
process's terminal as it is written. The run directory is bind-mounted into it, which is why there is
nothing to collect afterwards. Layers are built with `docker buildx` and prebuilt images are pulled.
"""

import json
import logging
import subprocess
import tempfile
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import get_args, override

from ssebench import stack
from ssebench.arch import platform_args
from ssebench.backends.base import (
    PAIR_LABEL,
    RUN_ID_LABEL,
    STOP_GRACE_SECONDS,
    Backend,
    BackendError,
    ImageRequest,
    Images,
    ImageUnavailableError,
    Mount,
    RunHandle,
    RunInfo,
    RunSpec,
    RunState,
    SidecarPair,
    describe_command,
)
from ssebench.backends.images import prebuilt_images
from ssebench.middleware import SidecarToolLayerAgentRuntime, SidecarToolLayerEnvironment, ToolLayerContext
from ssebench.pipe import build_pipe

logger = logging.getLogger(__name__)

CONTAINER_ID_WAIT_SECONDS = 10
"""How long `stop` waits for `docker run` to create the container it is meant to stop."""


@dataclass(kw_only=True)
class DockerRun(RunHandle):
    """A run on the Docker daemon.

    `process` is the foreground `docker run` of the container the run waits for; a run found by
    `list_runs` has none and is identified by `container`.
    """

    process: subprocess.Popen[bytes] | None = None
    cidfile: Path | None = None
    """Where `docker run` writes the container's ID once it exists."""
    scratch: tempfile.TemporaryDirectory[str] | None = field(default=None, repr=False)
    container: str = ""
    pair: SidecarPair | None = None
    removes_itself: bool = False
    """Whether Docker removes the container when it exits (`--rm`)."""


class DockerBackend(Backend):
    """Runs on the Docker daemon that the `docker` CLI is set up for.

    `network` names a Docker network for every run to join; by default it is the network of the LiteLLM
    stack that matches the run's egress policy.
    """

    name = "docker"
    builds_images = True
    supports_exec = True

    def __init__(self, network: str | None = None) -> None:
        self.network = network

    # ==================== images ====================

    @override
    def prepare_images(self, request: ImageRequest) -> Images:
        if request.prebuilt:
            images = prebuilt_images(request)
            for image in {images.agent, images.environment} - {None}:
                assert image is not None
                self._pull(image, request.task.platform)
            return images
        return self._build(request)

    def _build(self, request: ImageRequest) -> Images:
        task, agent = request.task, request.agent
        context = ToolLayerContext(
            task_name=task.name,
            source_dir=task.get_task_metadata().source,
            plugins=request.plugins,
            platform=task.platform,
        )
        if request.mode == "sandbox":
            assert request.tool_layer is not None
            image = build_pipe([task, request.tool_layer(context), agent])
            logger.info(f"Build benchmark image {image}")
            return Images(agent=image)

        agent_image = build_pipe([SidecarToolLayerAgentRuntime(context), agent])
        logger.info(f"Built agent image {agent_image}")
        environment_image = build_pipe([task, SidecarToolLayerEnvironment(context)])
        logger.info(f"Built environment image {environment_image}")
        return Images(agent=agent_image, environment=environment_image)

    def _pull(self, image: str, platform: str | None) -> None:
        logger.info(f"Pulling {image}")
        pull = subprocess.run(["docker", "pull", *platform_args(platform), image], capture_output=True, text=True)
        if pull.returncode == 0:
            return
        present = subprocess.run(["docker", "image", "inspect", image], capture_output=True)
        if present.returncode != 0:
            raise ImageUnavailableError(
                f"The prebuilt image {image} is not in the registry or on this machine: {pull.stderr.strip()}"
            )
        logger.warning(f"Could not pull {image}; using the copy on this machine: {pull.stderr.strip()}")

    @override
    def copy_from_image(self, image: str, path: PurePosixPath, dest: Path, platform: str | None = None) -> None:
        create = subprocess.run(
            ["docker", "create", *platform_args(platform), image, "true"], capture_output=True, text=True
        )
        if create.returncode != 0:
            raise RuntimeError(f"Could not create a container from {image}: {create.stderr.strip()}")
        container = create.stdout.strip()
        try:
            copy = subprocess.run(
                ["docker", "cp", "--follow-link", f"{container}:{path}", str(dest)], capture_output=True, text=True
            )
            if copy.returncode != 0:
                raise RuntimeError(f"Could not copy {path} from {image}: {copy.stderr.strip()}")
        finally:
            _ = subprocess.run(["docker", "rm", container], capture_output=True)

    # ==================== commands ====================

    def _network(self, spec: RunSpec) -> str:
        return self.network or stack.run_network(spec.network.egress)

    @staticmethod
    def _mount_options(mounts: list[Mount]) -> list[str]:
        """`docker run` options for `mounts`. A read-only mount uses `--mount`, which refuses a source that is missing."""
        options: list[str] = []
        for mount in mounts:
            if mount.read_only:
                options += ["--mount", f"type={mount.kind},source={mount.source},target={mount.target},readonly"]
            else:
                options += ["-v", f"{mount.source}:{mount.target}"]
        return options

    @staticmethod
    def _env_options(env: Mapping[str, str]) -> list[str]:
        return [option for name, value in env.items() for option in ("-e", f"{name}={value}")]

    @staticmethod
    def _label_options(labels: Mapping[str, str]) -> list[str]:
        return [option for name, value in labels.items() for option in ("--label", f"{name}={value}")]

    def _pair_options(self, spec: RunSpec, pair: SidecarPair) -> list[str]:
        """The options both containers of a pair share."""
        return [
            *platform_args(spec.platform),
            "--network",
            self._network(spec),
            *self._label_options({PAIR_LABEL: pair.run_id}),
            *self._env_options(pair.shared_env()),
            *self._mount_options(pair.shared_mounts(spec.results, spec.archive)),
        ]

    def environment_options(self, spec: RunSpec) -> list[str]:
        """`docker run` options of the environment container of a sidecar run, before its image."""
        assert spec.sidecar is not None
        pair = spec.sidecar
        return [
            "--name",
            pair.environment_name,
            *self._pair_options(spec, pair),
            *self._env_options(pair.environment_env()),
            *self._label_options(spec.labels),
        ]

    def agent_options(self, spec: RunSpec) -> list[str]:
        """`docker run` options of the container the run waits for, before its image."""
        if spec.sidecar is not None:
            return [
                *self._pair_options(spec, spec.sidecar),
                *self._env_options(spec.env),
                *self._mount_options(list(spec.artifacts)),
            ]
        return [
            *platform_args(spec.platform),
            "--network",
            self._network(spec),
            *self._env_options(spec.env),
            *self._mount_options([spec.results, spec.archive, *spec.artifacts]),
            *self._label_options(spec.labels),
        ]

    def run_command(self, spec: RunSpec) -> list[str]:
        """The `docker run` command of the container the run waits for."""
        return ["docker", "run", *([] if spec.keep else ["--rm"]), *self.agent_options(spec), spec.image]

    def environment_command(self, spec: RunSpec) -> list[str]:
        """The `docker run` command of the environment container of a sidecar run."""
        assert spec.sidecar is not None
        return ["docker", "run", "--detach", *self.environment_options(spec), spec.sidecar.environment_image]

    # ==================== the run ====================

    @override
    def start(self, spec: RunSpec) -> RunHandle:
        pair = spec.sidecar
        if pair is not None:
            try:
                self.create_volumes(pair)
                # The empty source volume takes the project from the environment image, so that container
                # starts first; the agent container's entrypoint waits for the daemon.
                logger.info(f"Starting environment {pair.environment_name} (run {pair.run_id})")
                self._docker(
                    self.environment_command(spec), f"Starting the environment container {pair.environment_name}"
                )
            except BackendError:
                self.remove_pair(pair)
                raise

        scratch = tempfile.TemporaryDirectory(prefix="ssebench-run-")
        cidfile = Path(scratch.name) / "cid"
        command = self.run_command(spec)
        try:
            process = subprocess.Popen([*command[:2], "--cidfile", str(cidfile), *command[2:]])
        except BaseException:
            scratch.cleanup()
            if pair is not None:
                self.remove_pair(pair)
            raise
        return DockerRun(
            run_id=spec.run_id,
            name=pair.environment_name if pair else "",
            keep=spec.keep,
            process=process,
            cidfile=cidfile,
            scratch=scratch,
            pair=pair,
            removes_itself=not spec.keep,
        )

    @staticmethod
    def _docker(command: list[str], what: str) -> None:
        try:
            _ = subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        except subprocess.CalledProcessError as e:
            # The command line can hold the run's model key, so only its first words are reported.
            detail = (e.stderr or "").strip()
            raise BackendError(
                f"{what} failed: `{describe_command(command)}` exited with status {e.returncode}"
                + (f": {detail}" if detail else "")
            ) from e

    def _container_id(self, handle: DockerRun) -> str:
        """The ID of the container being waited on, once `docker run` has created it; empty if none."""
        if handle.container:
            return handle.container
        if handle.cidfile is None:
            return ""
        deadline = time.monotonic() + CONTAINER_ID_WAIT_SECONDS
        while True:
            try:
                container = handle.cidfile.read_text().strip()
            except OSError:
                container = ""
            if container or time.monotonic() >= deadline:
                handle.container = container
                return container
            time.sleep(0.1)

    @override
    def wait(self, handle: RunHandle, timeout: float | None = None) -> int:
        assert isinstance(handle, DockerRun)
        if handle.process is None:
            waited = subprocess.run(["docker", "wait", handle.container], capture_output=True, text=True)
            if waited.returncode != 0:
                raise BackendError(f"Could not wait for {handle.container}: {waited.stderr.strip()}")
            return int(waited.stdout.strip())
        try:
            return handle.process.wait(timeout)
        except subprocess.TimeoutExpired:
            raise TimeoutError(f"The run {handle.run_id} is still running after {timeout} seconds") from None
        except BaseException:
            handle.process.kill()
            raise

    @override
    def logs(self, handle: RunHandle, *, follow: bool = False) -> Iterator[str]:
        assert isinstance(handle, DockerRun)
        container = self._container_id(handle)
        if not container:
            raise BackendError(f"The run {handle.run_id} has no container")
        command = ["docker", "logs", *(["--follow"] if follow else []), container]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        assert process.stdout is not None
        try:
            yield from process.stdout
        finally:
            if process.poll() is None:
                process.terminate()
            process.stdout.close()
            _ = process.wait()
        if process.returncode != 0:
            raise BackendError(
                f"Could not read the logs of {container}: `docker logs` exited with {process.returncode}"
            )

    @override
    def collect_results(self, handle: RunHandle, dest: Path) -> None:
        # The run directory is bind-mounted into the container, so the results are in place.
        logger.debug(f"The results of run {handle.run_id} are already in {dest}")

    @override
    def stop(self, handle: RunHandle, grace: int = STOP_GRACE_SECONDS) -> None:
        assert isinstance(handle, DockerRun)
        container = self._container_id(handle)
        if container:
            _ = subprocess.run(["docker", "stop", "--time", str(grace), container], capture_output=True, text=True)

    @override
    def cleanup(self, handle: RunHandle) -> None:
        assert isinstance(handle, DockerRun)
        if handle.scratch is not None:
            handle.scratch.cleanup()
            handle.scratch = None
        if handle.keep:
            if handle.pair is not None:
                logger.info(f"Kept the containers and volumes labelled {PAIR_LABEL}={handle.pair.run_id}")
            return
        if handle.pair is not None:
            self.remove_pair(handle.pair)
        elif handle.process is None and handle.container:
            self._best_effort(["docker", "rm", "--force", handle.container])

    # ==================== reaching a run ====================

    @override
    def endpoint(self, handle: RunHandle, port: int) -> str:
        """The container's address on its Docker network, which a host with a Linux bridge can route to.

        Docker Desktop keeps that network inside a virtual machine; the address does not work there.
        """
        assert isinstance(handle, DockerRun)
        container = self._container_id(handle)
        if not container:
            raise BackendError(f"The run {handle.run_id} has no container")
        inspected = subprocess.run(
            ["docker", "inspect", "--type", "container", container], capture_output=True, text=True
        )
        if inspected.returncode != 0:
            raise BackendError(f"Could not inspect {container}: {inspected.stderr.strip()}")
        entry = json.loads(inspected.stdout)[0]
        if not entry.get("State", {}).get("Running"):
            raise BackendError(f"The run {handle.run_id} is not running")
        for network in (entry.get("NetworkSettings", {}).get("Networks") or {}).values():
            if network.get("IPAddress"):
                return f"http://{network['IPAddress']}:{port}"
            if network.get("GlobalIPv6Address"):
                return f"http://[{network['GlobalIPv6Address']}]:{port}"
        raise BackendError(f"The run {handle.run_id} has no address on a Docker network")

    @override
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
        assert isinstance(handle, DockerRun)
        container = self._container_id(handle)
        if not container:
            raise BackendError(f"The run {handle.run_id} has no container")
        return [
            "docker",
            "exec",
            *(["--interactive"] if stdin or tty else []),
            *(["--tty"] if tty else []),
            *(["--user", user] if user else []),
            *(["--workdir", workdir] if workdir else []),
            # `-e NAME` takes the value from the docker client's own environment.
            *[option for name in env_names for option in ("--env", name)],
            container,
            *command,
        ]

    # ==================== sidecar pairs ====================

    def create_volumes(self, pair: SidecarPair) -> None:
        """Create the run-scoped volumes of `pair`."""
        for volume in pair.volumes:
            self._docker(
                ["docker", "volume", "create", "--label", f"{PAIR_LABEL}={pair.run_id}", volume],
                f"Creating the volume {volume}",
            )

    def remove_pair(self, pair: SidecarPair) -> None:
        """Remove the environment container and the volumes of `pair`; best effort."""
        self._best_effort(["docker", "rm", "--force", pair.environment_name])
        self._best_effort(["docker", "volume", "rm", *pair.volumes])

    @staticmethod
    def _best_effort(command: list[str]) -> None:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning(f"Failed to clean up: {result.stderr.strip()}")

    # ==================== finding runs ====================

    @override
    def list_runs(self, labels: Mapping[str, str] | None = None) -> list[RunInfo]:
        filters = [option for name, value in (labels or {}).items() for option in ("--filter", f"label={name}={value}")]
        listed = subprocess.run(
            ["docker", "ps", "--all", "--quiet", "--no-trunc", *filters], capture_output=True, text=True
        )
        if listed.returncode != 0:
            raise BackendError(f"Could not list the runs: {listed.stderr.strip()}")
        containers = listed.stdout.split()
        if not containers:
            return []
        inspected = subprocess.run(["docker", "inspect", *containers], capture_output=True, text=True)
        if inspected.returncode != 0:
            raise BackendError(f"Could not inspect the runs: {inspected.stderr.strip()}")
        return [self._info(entry) for entry in json.loads(inspected.stdout)]

    @staticmethod
    def _info(entry: dict[str, object]) -> RunInfo:
        config = entry.get("Config")
        state = entry.get("State")
        config = config if isinstance(config, dict) else {}
        state = state if isinstance(state, dict) else {}
        labels = {str(k): str(v) for k, v in (config.get("Labels") or {}).items()}
        status = str(state.get("Status", ""))
        run_state: RunState = "unknown"
        for known in get_args(RunState):
            if status == known:
                run_state = known
        container = str(entry.get("Id", ""))
        run_id = labels.get(RUN_ID_LABEL, "")
        return RunInfo(
            run_id=run_id,
            name=str(entry.get("Name", "")).lstrip("/"),
            state=run_state,
            exit_code=int(str(state["ExitCode"])) if run_state == "exited" and "ExitCode" in state else None,
            image=str(config.get("Image", "")),
            labels=labels,
            created_at=str(entry["Created"]) if entry.get("Created") else None,
            handle=DockerRun(run_id=run_id, name=str(entry.get("Name", "")).lstrip("/"), container=container),
        )
