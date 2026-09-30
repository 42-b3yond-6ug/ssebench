"""The local demo: the Compose stack with the task catalog and the web UI, and one run to look at.

`up` starts the LiteLLM proxy, its database, the catalog and the web UI in their own Compose
project, runs one agent on one pilot task with `--keep-container`, and leaves the finished run in
the web UI, which lists kept containers. The default agent, `reference`, applies the task's known
fix and needs no model or key. `down` removes everything the demo created.

The demo has a Compose project of its own (`SSEBENCH_DEMO_PROJECT`), never the one of a stack that
you run yourself, because `down` deletes the project's volume. It shares the Docker daemon with
everything else: `down` removes only the demo project, and the task containers on its networks.
"""

import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from ssebench import arch, doctor, paths, settings, stack
from ssebench.agents.agent import get_agent_path
from ssebench.doctor import Status
from ssebench.middleware.tools import RUNTIME_IMAGE_ENV, runtime_image
from ssebench.models import NO_MODEL
from ssebench.pipe import REGISTRY, TAG
from ssebench.runner.layout import new_run_id, run_dir
from ssebench.runner.lifecycle import RUN_ID_LABEL
from ssebench.runner.reference import is_reference_run
from ssebench.tasks import Catalog, CatalogError, load_catalog
from ssebench.tasks.catalog import bundled_manifest
from ssebench.tasks.manifest import ManifestTask

DEFAULT_TASK = "gjson-196-bf4efcb"
DEFAULT_AGENT = "reference"
DEFAULT_PROJECT = "ssebench-demo"
DEFAULT_WEBUI_PORT = 3001
DEFAULT_CATALOG_PORT = 8090
DEFAULT_TIMEOUT = 3600

DEMO_LABEL = "ssebench.demo"
"""Label of the demo's catalog and web UI containers; a Compose project without it is not the demo's."""
RUN_LABEL = "ssebench.webui"
"""Label that the runner puts on every task container; the web UI lists containers by it."""
IMAGES = ("catalog", "webui")
"""The demo's own images, pulled from the registry or built from this checkout."""

PROJECT_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]*")
POLL_SECONDS = 1.0
START_SLACK_SECONDS = 1800
"""How long the demo waits for a run beyond the agent's timeout: building the task's images."""


class DemoError(RuntimeError):
    """The demo cannot continue; the message says what to do."""


def say(message: str = "") -> None:
    print(message, flush=True)


@dataclass(frozen=True)
class Demo:
    project: str
    litellm_port: int
    catalog_port: int
    webui_port: int

    @property
    def webui_url(self) -> str:
        return f"http://127.0.0.1:{self.webui_port}"

    @property
    def catalog_url(self) -> str:
        return f"http://127.0.0.1:{self.catalog_port}"

    @property
    def run_networks(self) -> list[str]:
        """The networks that a run container joins, for either egress policy."""
        return [stack.agents_network(), stack.network()]


def configure() -> Demo:
    """Read the demo's settings.

    Raises:
        DemoError: If the project name is not valid, or is the name of the stack you run yourself.
        settings.SettingError: If a port is not a port number.
    """
    project = settings.get("SSEBENCH_DEMO_PROJECT", DEFAULT_PROJECT)
    if not PROJECT_PATTERN.fullmatch(project):
        raise DemoError(
            f"SSEBENCH_DEMO_PROJECT={project!r} is not a Compose project name (lowercase letters, digits, - and _)"
        )
    if project == settings.compose_project():
        raise DemoError(
            f"SSEBENCH_DEMO_PROJECT and COMPOSE_PROJECT_NAME are both {project!r}. The demo deletes its project's "
            "volume when it stops, so it needs a project of its own: set SSEBENCH_DEMO_PROJECT to another name."
        )
    return Demo(
        project=project,
        litellm_port=settings.litellm_port(),
        catalog_port=settings.port("SSEBENCH_DEMO_CATALOG_PORT", DEFAULT_CATALOG_PORT),
        webui_port=settings.port("SSEBENCH_DEMO_WEBUI_PORT", DEFAULT_WEBUI_PORT),
    )


def activate(demo: Demo) -> None:
    """Make every `stack` call in this process, and in the `ssebench run` it starts, work on the demo's project."""
    os.environ["COMPOSE_PROJECT_NAME"] = demo.project


def docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True)


def container_ids(*filters: str) -> list[str]:
    """The IDs of the containers, running or not, that match every `docker ps --filter` in `filters`."""
    args = ["ps", "--all", "--quiet", *(arg for f in filters for arg in ("--filter", f))]
    result = docker(*args)
    if result.returncode != 0:
        raise DemoError(f"docker {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.split()


def project_label(demo: Demo) -> str:
    return f"label=com.docker.compose.project={demo.project}"


def check_project(demo: Demo) -> None:
    """Refuse to work on a Compose project that has containers the demo did not create.

    Raises:
        DemoError: If it does.
    """
    everything = container_ids(project_label(demo))
    ours = container_ids(project_label(demo), f"label={DEMO_LABEL}=true")
    if everything and not ours:
        raise DemoError(
            f"The Compose project {demo.project!r} has containers that the demo did not create. "
            "Set SSEBENCH_DEMO_PROJECT to a name that no other stack uses."
        )


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def check_ports(demo: Demo) -> None:
    """Fail early, and say which setting to change, when a port is taken by something else.

    Raises:
        DemoError: If a port is in use and the demo's own containers are not running.
    """
    if container_ids(project_label(demo), "status=running"):
        return  # a demo that is already up holds its own ports
    for name, port in (
        ("LITELLM_PORT", demo.litellm_port),
        ("SSEBENCH_DEMO_CATALOG_PORT", demo.catalog_port),
        ("SSEBENCH_DEMO_WEBUI_PORT", demo.webui_port),
    ):
        if not port_free(port):
            hint = (
                " If it is the LiteLLM proxy that `ssebench run` started, `ssebench proxy down` stops it."
                if name == "LITELLM_PORT"
                else ""
            )
            raise DemoError(
                f"Port {port} is in use. Choose another one with {name}, for example `{name}={port + 1} just demo`"
                f" (`{name}={port + 1} ssebench demo up` without a clone).{hint}"
            )


def host_network_check() -> doctor.Check | None:
    """A warning when Docker runs in a VM, where the web UI container's host network is not the machine's.

    The web UI reaches the daemon of a run by the container's address, and binds to loopback; both work
    only when the Docker engine shares the network namespace with the host (a native Linux engine) or
    Docker Desktop's opt-in host networking is on.
    """
    engine = doctor.run(["docker", "info", "--format", "{{.OperatingSystem}}"])[1]
    if platform.system() == "Linux" and "Docker Desktop" not in engine:
        return None
    return doctor.Check(
        "Host network",
        Status.WARN,
        "the web UI container shares the Docker engine's network, which only a Linux engine, or Docker "
        "Desktop with host networking turned on, makes reachable from this machine",
        "In Docker Desktop (4.34 or later), turn on Settings > Resources > Network > Enable host networking, "
        "then restart it. If the web UI still does not answer, run the demo on a Linux host.",
    )


def check_host(model: str | None) -> None:
    """Print the doctor's checks for what the demo needs, and stop if one fails.

    Raises:
        DemoError: If a required check fails.
    """
    checks = doctor.host_checks()
    if (network := host_network_check()) is not None:
        checks.append(network)
    if model is not None:
        checks.append(doctor.check_model_key(model))
    say(doctor.render(checks))
    if any(check.status is Status.FAIL for check in checks):
        raise DemoError("Fix the failed checks above, then run the demo again.")


def image_ref(name: str) -> str:
    return f"{REGISTRY}/{name}:{TAG}"


def image_exists(ref: str) -> bool:
    return docker("image", "inspect", "--format", "{{.Id}}", ref).returncode == 0


def pull(ref: str, platform: str | None = None) -> bool:
    """Pull an image, for `platform` if given; False when the registry does not have it or cannot be reached."""
    say(f"  pulling {ref}")
    began = time.monotonic()
    result = docker("pull", "--quiet", *arch.platform_args(platform), ref)
    if result.returncode == 0:
        say(f"  pulled in {format_duration(time.monotonic() - began)}")
        return True
    reason = (result.stderr.strip().splitlines() or ["unknown error"])[-1]
    say(f"  cannot pull it: {reason[:100]}{'...' if len(reason) > 100 else ''}")
    return False


def build_base(base: str, platform: str | None = None) -> None:
    """Build a base image, given its manifest name such as `base-generic-go:1.0.0`, and every tag a dataset pins.

    `platform` is what the case images built on it use; None builds for the Docker host's own.
    """
    target = base.split(":")[0].removeprefix("base-")
    if shutil.which("make") is None:
        raise DemoError(
            f"Building {base} needs make; install it, or use a registry that has the image (SSEBENCH_REGISTRY)."
        )
    _ = subprocess.run(
        [
            "make",
            "-C",
            str(paths.require_checkout(f"Building {base}") / "images" / "base-images"),
            *([f"BUILD_FLAGS=--platform {platform}"] if platform else []),
            target,
            f"SSEBENCH_REGISTRY={REGISTRY}",
        ],
        check=True,
    )


def prepare_images(catalog: Catalog, entry: ManifestTask, build: bool) -> str | None:
    """Get the images of the stack and of the task: pull them, or build them from this checkout.

    The LiteLLM image is always built here, as `ssebench proxy up` does: it carries this checkout's
    `models/`. The others are pulled first, at this checkout's version, and built when the registry
    does not have them, which is the case before a release or without network access. `build` skips
    the pull.

    Returns:
        The runtime image to build the run's tool layer from, which saves compiling the daemon,
        or None when the layer is built from source.

    Raises:
        subprocess.CalledProcessError: If a build fails.
    """
    _ = stack.build(stack.config_hash())
    wanted = [name for name in IMAGES if build or not image_exists(image_ref(name))]
    missing = [name for name in wanted if build or not pull(image_ref(name))]
    if missing:
        say(f"Building {', '.join(missing)} from this checkout...")
        _ = paths.require_checkout(f"Building the {' and '.join(missing)} image")
        stack.compose("build", *missing, overlays=[paths.demo_compose_file()])

    # The run's images all have the platform of the case image; see `Task.platform`.
    platform = arch.docker_platform(arch.run_arch(entry.arch))
    prepare_case_image(catalog, entry, build, platform)

    runtime = runtime_image()
    if not build and (image_exists(runtime) or pull(runtime, platform)):
        return runtime
    return None


def prepare_case_image(catalog: Catalog, entry: ManifestTask, build: bool, platform: str | None = None) -> None:
    """Make sure the run can get the task's case image: pulled, or built on its base image."""
    # The case image already holds its base image's layers. Only a local build of the case image
    # (the run does it when the pull fails) needs the base image. The run pulls the image by the
    # dataset version, as the catalog service's clients do, so this pulls that tag too.
    case = catalog.case_image(entry)
    if not build and pull(case, platform):
        return
    base = f"{REGISTRY}/{entry.base}"
    if image_exists(base) or (not build and pull(base, platform)):
        return
    say(f"Building {base} from this checkout...")
    build_base(entry.base, platform)


def wait_for(url: str, what: str, timeout: float = 120.0) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            if httpx.get(url, timeout=2.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        if time.monotonic() >= deadline:
            raise DemoError(
                f"{what} did not answer at {url} within {timeout:.0f}s. `docker compose logs` of the demo project shows why."
            )
        time.sleep(POLL_SECONDS)


def start_stack(demo: Demo) -> None:
    check_project(demo)
    stack.compose("up", "--detach", overlays=[paths.demo_compose_file()])
    stack.wait_healthy(reset="ssebench demo down")
    wait_for(f"{demo.catalog_url}/manifest.json", "The task catalog")
    wait_for(f"{demo.webui_url}/api/health", "The web UI")
    try:
        health: object = httpx.get(f"{demo.webui_url}/api/health", timeout=5.0).json()
    except (httpx.HTTPError, ValueError):
        health = None
    problem = runner_problem(health)
    if problem is not None:
        raise DemoError(problem)


def runner_problem(health: object) -> str | None:
    """Why the web UI cannot list runs, from its `/api/health` answer, or None when it can."""
    if isinstance(health, dict) and health.get("runner") is True:
        return None
    message = "The web UI cannot reach the Docker daemon through /var/run/docker.sock, so it could not list runs."
    detail = health.get("runnerError") if isinstance(health, dict) else None
    return f"{message} It reports: {detail}" if isinstance(detail, str) and detail else message


def run_containers(demo: Demo) -> list[str]:
    """The task containers of runs on the demo's networks, kept or not."""
    found: list[str] = []
    for network in demo.run_networks:
        found += container_ids(f"label={RUN_LABEL}=true", f"network={network}")
    return list(dict.fromkeys(found))


def remove_runs(demo: Demo) -> int:
    """Remove the demo's task containers; the number removed."""
    ids = run_containers(demo)
    if ids:
        result = docker("rm", "--force", *ids)
        if result.returncode != 0:
            raise DemoError(f"Could not remove the run containers: {result.stderr.strip()}")
    return len(ids)


def log_files() -> list[Path]:
    return sorted((paths.workspace() / "results").glob("demo-*.log"))


@dataclass(frozen=True)
class Plan:
    task: str
    agent: str
    model: str | None
    timeout: int
    build: bool
    run_id: str = field(default_factory=new_run_id)

    @property
    def result_file(self) -> Path:
        """Where the evaluator writes the grade; the runner finds it there and the demo waits for it."""
        model = NO_MODEL if is_reference_run(self.agent) else self.model
        assert model is not None
        return run_dir(self.task, self.agent, model, self.run_id, paths.workspace() / "results") / "result.json"

    def run_command(self, demo: Demo) -> list[str]:
        cmd = [
            sys.executable,
            "-m",
            "ssebench",
            "run",
            "--task",
            self.task,
            "--agent",
            self.agent,
            "--timeout",
            str(self.timeout),
            "--run-id",
            self.run_id,
            "--keep-container",
        ]
        if self.model is not None and not is_reference_run(self.agent):
            cmd += ["--model", self.model]
        # A local build of the case image needs no registry; otherwise the run pulls it and, when the
        # registry does not have it, builds it from the checkout.
        if self.build:
            cmd += ["--local", str(paths.require_checkout("Building the task's image").joinpath("datasets", "pilot"))]
        else:
            cmd += ["--catalog", demo.catalog_url]
        return cmd


def grade(path: Path, since: float) -> dict[str, object] | None:
    """The evaluator's result at `path`, once the run wrote it after `since`."""
    try:
        if path.stat().st_mtime < since:
            return None
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and "patch_result" in data else None


def describe(result: Mapping[str, object]) -> str:
    patch = result.get("patch_result")
    if not isinstance(patch, dict):
        return "no grade"

    def passed(ok: object) -> str:
        return "passed" if ok else "failed"

    parts = [
        f"build {passed(patch.get('build_success'))}",
        f"PoC {patch.get('pov_passed')}/{patch.get('pov_total')} passed",
        f"functional tests {passed(patch.get('func_test_success'))}",
        f"intent tests {passed(patch.get('intent_test_success'))}",
    ]
    return ", ".join(parts)


PROGRESS_LINE = re.compile(r"(INFO|WARNING|ERROR):[\w.]+:(.*)")
QUIET_SECONDS = 20
"""How long the demo stays silent before it says that the run is still going."""


class LogTail:
    """Follows the run's log and prints its progress messages.

    The log also holds BuildKit's output and the container's; those stay in the file. What the
    CLI itself logs (`INFO:ssebench...:message`) is the run's progress.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.offset = 0
        self.partial = b""
        self.last_output = time.monotonic()

    def show(self) -> None:
        with self.path.open("rb") as f:
            _ = f.seek(self.offset)
            data = f.read()
        self.offset += len(data)
        *lines, self.partial = (self.partial + data).split(b"\n")
        for raw in lines:
            match = PROGRESS_LINE.fullmatch(raw.decode(errors="replace").rstrip())
            if match is None:
                continue
            level, message = match.groups()
            say(f"  {message}" if level == "INFO" else f"  {level.lower()}: {message}")
            self.last_output = time.monotonic()

    def heartbeat(self, began: float) -> None:
        if time.monotonic() - self.last_output >= QUIET_SECONDS:
            say(f"  still working, {format_duration(time.monotonic() - began)} so far (details: {self.path})")
            self.last_output = time.monotonic()


def start_run(demo: Demo, plan: Plan, runtime_image: str | None) -> tuple[subprocess.Popen[bytes], Path]:
    """Start `ssebench run --keep-container` in its own session, with its output in a log file.

    The command returns only when the kept container stops, so the demo cannot wait for it. The
    process lives on after the demo returns, and ends when `down` removes the container.
    """
    log = paths.workspace() / "results" / f"demo-{int(time.time())}.log"
    log.parent.mkdir(exist_ok=True)
    env = {
        **os.environ,
        # `ssebench run` starts the stack with the base Compose file alone; the catalog and the
        # web UI are not part of it, and it need not warn about them.
        "COMPOSE_IGNORE_ORPHANS": "true",
        "PYTHONUNBUFFERED": "1",
    }
    if runtime_image is not None:
        env[RUNTIME_IMAGE_ENV] = runtime_image
    with log.open("wb") as out:
        process = subprocess.Popen(
            plan.run_command(demo),
            cwd=paths.workspace(),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return process, log


def wait_for_run(plan: Plan, process: subprocess.Popen[bytes], log: Path, started: float) -> dict[str, object]:
    """Show the run's log until the evaluator has written its grade; the grade.

    Raises:
        DemoError: If the run ends without a grade, or takes too long.
    """
    tail = LogTail(log)
    began = time.monotonic()
    deadline = began + plan.timeout + START_SLACK_SECONDS
    while True:
        tail.show()
        result = grade(plan.result_file, started)
        if result is not None:
            return result
        code = process.poll()
        if code is not None:
            tail.show()
            result = grade(plan.result_file, started)
            if result is not None:
                return result
            raise DemoError(f"The run ended with exit code {code} and no grade. Its log is {log}.")
        if time.monotonic() > deadline:
            raise DemoError(f"The run did not finish within {plan.timeout + START_SLACK_SECONDS}s. Its log is {log}.")
        tail.heartbeat(began)
        time.sleep(POLL_SECONDS)


def find_run(demo: Demo, plan: Plan) -> str | None:
    """The kept container of the run, as the web UI lists it."""
    for network in demo.run_networks:
        found = container_ids(
            f"label={RUN_LABEL}=true",
            f"label={RUN_ID_LABEL}={plan.run_id}",
            f"network={network}",
        )
        if found:
            return found[0]
    return None


def check_run_in_webui(demo: Demo, run_id: str) -> None:
    """Ask the web UI for the run's grade, as the browser does; the web UI names a run by its run ID.

    Raises:
        DemoError: If the web UI does not have it.
    """
    url = f"{demo.webui_url}/api/containers/{run_id}/result"
    deadline = time.monotonic() + 60
    while True:
        try:
            response = httpx.get(url, timeout=5.0)
            if response.status_code == 200 and response.json().get("available"):
                return
        except (httpx.HTTPError, ValueError):
            pass
        if time.monotonic() >= deadline:
            raise DemoError(f"The web UI does not show the finished run at {url}.")
        time.sleep(POLL_SECONDS)


def format_duration(seconds: float) -> str:
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes}m{secs:02d}s" if minutes else f"{secs}s"


def up(plan: Plan) -> int:
    """Start the stack, run `plan`, and leave the finished run in the web UI.

    Returns:
        The exit code of the command.
    """
    demo = configure()
    activate(demo)
    if plan.model is None and not is_reference_run(plan.agent):
        raise DemoError(f"--model is required, except with --agent {DEFAULT_AGENT}")
    _ = get_agent_path(plan.agent)
    try:
        catalog = load_catalog(str(bundled_manifest()))
        entry = catalog.task(plan.task)
    except (CatalogError, LookupError) as e:
        raise DemoError(str(e)) from e

    say("Checking this host")
    check_host(None if is_reference_run(plan.agent) else plan.model)
    check_project(demo)
    check_ports(demo)

    began = time.monotonic()
    say()
    say(
        f"Getting the images ({'building them from this checkout' if plan.build else 'pulling them, and building what the registry lacks'})"
    )
    runtime_image = prepare_images(catalog, entry, plan.build)
    images_done = time.monotonic()

    say()
    say(f"Starting the stack (Compose project {demo.project})")
    start_stack(demo)
    stack_done = time.monotonic()
    say()
    say(f"Web UI:  {demo.webui_url}")
    say(f"Catalog: {demo.catalog_url}/tasks")
    say(f"LiteLLM: {stack.host_url()}")

    say()
    replaced = remove_runs(demo)
    if replaced:
        say(f"Removed {replaced} run container(s) of an earlier demo.")
    for old in log_files():
        old.unlink(missing_ok=True)
    if is_reference_run(plan.agent):
        say(
            f"Running the reference agent on {plan.task}: it applies the task's known fix, so it needs no model and no key."
        )
    else:
        say(
            f"Running {plan.agent} with {plan.model} on {plan.task}. This calls the model with your key and costs money; "
            f"the run is live in the web UI, and stops after {format_duration(plan.timeout)} at the latest."
        )
    started = time.time()
    process, log = start_run(demo, plan, runtime_image)
    say(f"Its full log is {log}.")
    say()
    try:
        result = wait_for_run(plan, process, log, started)
    except KeyboardInterrupt:
        os.killpg(process.pid, signal.SIGTERM)
        say()
        say("Interrupted. The stack is still running; `ssebench demo down` removes it.")
        return 130
    except DemoError:
        say()
        say("The last lines of the run's log:")
        say("\n".join(log.read_text(errors="replace").splitlines()[-30:]))
        say()
        say("The stack is still running, so you can look around; `ssebench demo down` removes it.")
        raise
    run_done = time.monotonic()

    if find_run(demo, plan) is None:
        raise DemoError(f"The run finished, but its container is gone. Its log is {log}.")
    check_run_in_webui(demo, plan.run_id)

    say()
    say(
        f"Done in {format_duration(run_done - began)} (images {format_duration(images_done - began)}, "
        f"stack {format_duration(stack_done - images_done)}, run {format_duration(run_done - stack_done)})."
    )
    say(f"Result:  {describe(result)}")
    say()
    say(f"Open {demo.webui_url}")
    say(f"The run {plan.task} / {plan.agent} is listed there, with its dialog, diff and evaluation result.")
    say(
        "`just demo-down` (`ssebench demo down` without a clone) stops the demo and removes what it created: "
        "the stack, its volume and the kept container."
    )
    say("Results stay in results/; the images stay cached, so the next demo starts faster.")
    return 0


def down() -> int:
    """Remove the demo's task containers, its Compose project and the project's volume.

    Returns:
        The exit code of the command.
    """
    demo = configure()
    activate(demo)
    check_project(demo)
    say(f"Removing the run containers on the networks of {demo.project}")
    removed = remove_runs(demo)
    say(f"  removed {removed}")
    say(f"Removing the Compose project {demo.project} with its volume")
    # `down` reads no secret, but the base file requires them, even when `.env` is gone.
    for name in stack.REQUIRED_SECRETS:
        if not settings.get(name):
            os.environ[name] = "unused"
    stack.compose("down", "--volumes", "--remove-orphans", overlays=[paths.demo_compose_file()])
    for old in log_files():
        old.unlink(missing_ok=True)
    say("Done. results/ and the cached images stay.")
    return 0
