import json
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from ssebench import arch, demo, doctor, paths, settings, stack
from ssebench.doctor import Status
from ssebench.middleware.tools import RUNTIME_IMAGE_ENV
from ssebench.pipe import REGISTRY, TAG
from ssebench.tasks import Catalog, load_catalog
from ssebench.tasks.manifest import ManifestTask

CHECKOUT = Path(__file__).resolve().parents[2]
TASK = "gjson-196-bf4efcb"
VARIABLES = (
    "COMPOSE_PROJECT_NAME",
    "LITELLM_PORT",
    "SSEBENCH_DEMO_PROJECT",
    "SSEBENCH_DEMO_CATALOG_PORT",
    "SSEBENCH_DEMO_WEBUI_PORT",
    "LITELLM_MASTER_KEY",
    "POSTGRES_PASSWORD",
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(paths.HOME_ENV, str(CHECKOUT))
    monkeypatch.setattr(settings, "dotenv", dict)
    # An empty value counts as unset. Setting it, rather than deleting, also makes the monkeypatch
    # restore the variables that configure() and down() write to the environment.
    for name in VARIABLES:
        monkeypatch.setenv(name, "")


@pytest.fixture
def catalog() -> Catalog:
    return load_catalog(str(CHECKOUT / "datasets" / "pilot" / "manifest.json"))


@pytest.fixture
def entry(catalog: Catalog) -> ManifestTask:
    return catalog.task(TASK)


class FakeDocker:
    """Answers the docker, compose and make commands of the demo, and records them."""

    def __init__(self) -> None:
        self.images: set[str] = set()
        self.pullable: set[str] = set()
        self.listing: dict[frozenset[str], list[str]] = {}
        self.commands: list[list[str]] = []

    def __call__(self, cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.commands.append(cmd)
        done = subprocess.CompletedProcess[str]
        if cmd[:3] == ["docker", "image", "inspect"]:
            return done(cmd, 0 if cmd[-1] in self.images else 1, "", "No such image")
        if cmd[:2] == ["docker", "pull"]:
            if cmd[-1] in self.pullable:
                self.images.add(cmd[-1])
                return done(cmd, 0, "", "")
            return done(cmd, 1, "", "Error response from daemon: pull access denied")
        if cmd[:3] == ["docker", "ps", "--all"]:
            filters = frozenset(cmd[i + 1] for i, arg in enumerate(cmd) if arg == "--filter")
            return done(cmd, 0, "\n".join(self.listing.get(filters, [])), "")
        return done(cmd, 0, "", "")

    def matching(self, *prefix: str) -> list[list[str]]:
        return [cmd for cmd in self.commands if cmd[: len(prefix)] == list(prefix)]

    def compose(self, verb: str) -> list[list[str]]:
        return [cmd for cmd in self.commands if cmd[:2] == ["docker", "compose"] and verb in cmd]


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeDocker:
    docker = FakeDocker()
    monkeypatch.setattr(subprocess, "run", docker)
    monkeypatch.setattr(demo.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(stack, "build", lambda current, force=False: False)
    return docker


def engine(monkeypatch: pytest.MonkeyPatch, system: str, operating_system: str) -> None:
    monkeypatch.setattr(demo.platform, "system", lambda: system)
    monkeypatch.setattr(doctor, "run", lambda cmd: (0, operating_system))


@pytest.mark.parametrize("operating_system", ["Ubuntu 24.04.2 LTS", "NixOS 25.05 (Warbler)", ""])
def test_a_native_linux_engine_needs_no_host_network_warning(
    monkeypatch: pytest.MonkeyPatch, operating_system: str
) -> None:
    engine(monkeypatch, "Linux", operating_system)
    assert demo.host_network_check() is None


@pytest.mark.parametrize(
    ("system", "operating_system"),
    [("Darwin", "Docker Desktop"), ("Linux", "Docker Desktop"), ("Windows", "Docker Desktop")],
)
def test_a_vm_engine_gets_a_host_network_warning_that_names_the_setting(
    monkeypatch: pytest.MonkeyPatch, system: str, operating_system: str
) -> None:
    engine(monkeypatch, system, operating_system)
    check = demo.host_network_check()
    assert check is not None
    assert check.status is Status.WARN
    assert "Enable host networking" in check.fix


def test_defaults() -> None:
    d = demo.configure()

    assert (d.project, d.litellm_port, d.catalog_port, d.webui_port) == ("ssebench-demo", 4000, 8090, 3001)
    assert d.webui_url == "http://127.0.0.1:3001"

    demo.activate(d)

    # The stack helpers now work on the demo's project.
    assert stack.agents_network() == "ssebench-demo_agents"
    assert d.run_networks == ["ssebench-demo_agents", "ssebench-demo_default"]


def test_settings_override_the_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SSEBENCH_DEMO_PROJECT", "mine")
    monkeypatch.setenv("SSEBENCH_DEMO_WEBUI_PORT", "4741")
    monkeypatch.setenv("LITELLM_PORT", "4711")

    d = demo.configure()

    assert (d.project, d.webui_port, d.litellm_port) == ("mine", 4741, 4711)


def test_the_demo_needs_a_project_of_its_own(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "mine")
    monkeypatch.setenv("SSEBENCH_DEMO_PROJECT", "mine")

    with pytest.raises(demo.DemoError, match="project of its own"):
        demo.configure()


def test_the_default_demo_project_is_not_the_default_stack() -> None:
    assert demo.DEFAULT_PROJECT != settings.DEFAULT_COMPOSE_PROJECT


@pytest.mark.parametrize("name", ["Upper", "-dash", "has space", ""])
def test_project_names_are_validated(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setenv("SSEBENCH_DEMO_PROJECT", name)

    if name == "":
        assert demo.configure().project == demo.DEFAULT_PROJECT
    else:
        with pytest.raises(demo.DemoError, match="not a Compose project name"):
            demo.configure()


def test_a_port_setting_must_be_a_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SSEBENCH_DEMO_CATALOG_PORT", "http")

    with pytest.raises(settings.SettingError, match="SSEBENCH_DEMO_CATALOG_PORT"):
        demo.configure()


def test_project_with_foreign_containers_is_refused(fake: FakeDocker) -> None:
    d = demo.configure()
    fake.listing[frozenset({demo.project_label(d)})] = ["abc123"]

    with pytest.raises(demo.DemoError, match="did not create"):
        demo.check_project(d)


def test_project_with_demo_containers_or_none_is_accepted(fake: FakeDocker) -> None:
    d = demo.configure()
    demo.check_project(d)

    fake.listing[frozenset({demo.project_label(d)})] = ["abc123", "def456"]
    fake.listing[frozenset({demo.project_label(d), f"label={demo.DEMO_LABEL}=true"})] = ["abc123"]
    demo.check_project(d)


def test_down_refuses_a_foreign_project(fake: FakeDocker) -> None:
    d = demo.configure()
    fake.listing[frozenset({demo.project_label(d)})] = ["abc123"]

    with pytest.raises(demo.DemoError):
        demo.down()
    assert fake.compose("down") == []
    assert fake.matching("docker", "rm") == []


def test_down_removes_runs_then_the_project_with_its_volume(fake: FakeDocker) -> None:
    d = demo.configure()
    project = frozenset({demo.project_label(d)})
    fake.listing[project] = ["c1"]
    fake.listing[project | {f"label={demo.DEMO_LABEL}=true"}] = ["c1"]
    fake.listing[frozenset({f"label={demo.RUN_LABEL}=true", "network=ssebench-demo_agents"})] = ["run1", "run2"]
    fake.listing[frozenset({f"label={demo.RUN_LABEL}=true", "network=ssebench-demo_default"})] = ["run2", "run3"]

    assert demo.down() == 0

    [rm] = fake.matching("docker", "rm")
    assert rm == ["docker", "rm", "--force", "run1", "run2", "run3"]
    [down] = fake.compose("down")
    assert down[down.index("--project-name") + 1] == "ssebench-demo"
    assert down[-3:] == ["--volumes", "--remove-orphans"] or "--volumes" in down
    files = [down[i + 1] for i, arg in enumerate(down) if arg == "--file"]
    assert [Path(f).name for f in files] == ["docker-compose.yaml", "demo.yaml"]
    assert fake.commands.index(rm) < fake.commands.index(down)


def test_down_needs_no_secrets(fake: FakeDocker, monkeypatch: pytest.MonkeyPatch) -> None:
    demo.down()

    assert demo.os.environ["LITELLM_MASTER_KEY"] == "unused"


def test_images_are_pulled_and_a_pulled_case_image_needs_no_base(
    fake: FakeDocker, catalog: Catalog, entry: ManifestTask
) -> None:
    runtime = f"{REGISTRY}/runtime:{TAG}"
    fake.pullable = {f"{REGISTRY}/catalog:{TAG}", f"{REGISTRY}/webui:{TAG}", catalog.case_image(entry), runtime}

    assert demo.prepare_images(catalog, entry, build=False) == runtime

    assert fake.compose("build") == []
    assert fake.matching("make") == []
    assert [cmd[-1] for cmd in fake.matching("docker", "pull")] == [
        f"{REGISTRY}/catalog:{TAG}",
        f"{REGISTRY}/webui:{TAG}",
        catalog.case_image(entry),
        runtime,
    ]


def test_images_the_registry_lacks_are_built(fake: FakeDocker, catalog: Catalog, entry: ManifestTask) -> None:
    assert demo.prepare_images(catalog, entry, build=False) is None

    [build] = fake.compose("build")
    assert build[-2:] == ["catalog", "webui"]
    [make] = fake.matching("make")
    assert make[-2:] == ["generic-go", f"SSEBENCH_REGISTRY={REGISTRY}"]


@pytest.mark.parametrize("machine", ["aarch64", "x86_64"])
def test_the_task_images_are_pulled_and_built_for_the_platform_of_the_run(
    fake: FakeDocker, catalog: Catalog, entry: ManifestTask, monkeypatch: pytest.MonkeyPatch, machine: str
) -> None:
    monkeypatch.setattr(arch.platform, "machine", lambda: machine)
    runtime = f"{REGISTRY}/runtime:{TAG}"
    fake.pullable = {f"{REGISTRY}/catalog:{TAG}", f"{REGISTRY}/webui:{TAG}", runtime}

    _ = demo.prepare_images(catalog, entry, build=False)

    platform_flag = "linux/amd64"  # every pilot task is amd64-only
    pulls = {cmd[-1]: cmd[:-1] for cmd in fake.matching("docker", "pull")}
    # The stack's own images are multi-platform and run natively; the task's are pulled for its platform.
    assert "--platform" not in pulls[f"{REGISTRY}/catalog:{TAG}"]
    assert pulls[catalog.case_image(entry)][-2:] == ["--platform", platform_flag]
    assert pulls[f"{REGISTRY}/{entry.base}"][-2:] == ["--platform", platform_flag]
    assert pulls[runtime][-2:] == ["--platform", platform_flag]
    [make] = fake.matching("make")
    assert f"BUILD_FLAGS=--platform {platform_flag}" in make


def test_only_the_missing_images_are_pulled_or_built(fake: FakeDocker, catalog: Catalog, entry: ManifestTask) -> None:
    fake.images = {f"{REGISTRY}/catalog:{TAG}", f"{REGISTRY}/{entry.base}"}

    _ = demo.prepare_images(catalog, entry, build=False)

    [build] = fake.compose("build")
    assert build[-1] == "webui"
    assert f"{REGISTRY}/catalog:{TAG}" not in [cmd[-1] for cmd in fake.matching("docker", "pull")]
    assert fake.matching("make") == []


def test_build_skips_every_pull(fake: FakeDocker, catalog: Catalog, entry: ManifestTask) -> None:
    fake.pullable = {
        f"{REGISTRY}/catalog:{TAG}",
        f"{REGISTRY}/webui:{TAG}",
        catalog.case_image(entry),
        f"{REGISTRY}/runtime:{TAG}",
    }

    assert demo.prepare_images(catalog, entry, build=True) is None

    assert fake.matching("docker", "pull") == []
    [build] = fake.compose("build")
    assert build[-2:] == ["catalog", "webui"]
    assert len(fake.matching("make")) == 1


def test_building_a_base_image_needs_make(
    fake: FakeDocker, catalog: Catalog, entry: ManifestTask, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(demo.shutil, "which", lambda name: None)

    with pytest.raises(demo.DemoError, match="needs make"):
        _ = demo.prepare_images(catalog, entry, build=False)


def test_the_run_builds_its_tool_layer_from_the_published_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    started: list[dict[str, Any]] = []

    class Popen:
        pid = 1

        def __init__(self, cmd: list[str], **kwargs: Any) -> None:
            started.append(kwargs["env"])

    monkeypatch.setattr(demo.subprocess, "Popen", Popen)
    monkeypatch.setattr(paths, "home", lambda: tmp_path)
    d = demo.configure()
    plan = demo.Plan(task=TASK, agent="reference", model=None, timeout=60, build=False)

    _ = demo.start_run(d, plan, f"{REGISTRY}/runtime:{TAG}")
    _ = demo.start_run(d, plan, None)

    assert started[0][RUNTIME_IMAGE_ENV] == f"{REGISTRY}/runtime:{TAG}"
    assert RUNTIME_IMAGE_ENV not in started[1]
    assert started[0]["COMPOSE_IGNORE_ORPHANS"] == "true"


def test_reference_run_command_names_no_model() -> None:
    d = demo.configure()
    plan = demo.Plan(task=TASK, agent="reference", model="ignored", timeout=600, build=False, run_id="demo-run")

    cmd = plan.run_command(d)

    assert cmd[cmd.index("--agent") + 1] == "reference"
    assert "--model" not in cmd
    assert "--keep-container" in cmd
    assert cmd[cmd.index("--catalog") + 1] == "http://127.0.0.1:8090"
    assert cmd[cmd.index("--timeout") + 1] == "600"
    assert cmd[cmd.index("--run-id") + 1] == "demo-run"
    assert plan.result_file == CHECKOUT / "results" / TASK / "none" / "reference" / "demo-run" / "result.json"


def test_agent_run_command_names_the_model_and_a_local_build_uses_the_dataset() -> None:
    d = demo.configure()
    plan = demo.Plan(task=TASK, agent="claude-code", model="claude-sonnet-4-6", timeout=3600, build=True, run_id="r1")

    cmd = plan.run_command(d)

    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-4-6"
    assert cmd[cmd.index("--local") + 1] == str(CHECKOUT / "datasets" / "pilot")
    assert "--catalog" not in cmd
    assert plan.result_file.parts[-4:] == ("claude-sonnet-4-6", "claude-code", "r1", "result.json")


def test_a_grade_written_before_the_run_started_is_not_this_run_s(tmp_path: Path) -> None:
    result = tmp_path / "result.json"
    _ = result.write_text(json.dumps({"patch_result": {"build_success": True}}))
    before = time.time() - 10

    assert demo.grade(result, since=before) is not None
    assert demo.grade(result, since=time.time() + 10) is None


def test_grade_waits_for_a_complete_result(tmp_path: Path) -> None:
    result = tmp_path / "result.json"

    assert demo.grade(result, since=0) is None  # no file
    _ = result.write_text("")
    assert demo.grade(result, since=0) is None  # the runner touches it before the evaluator writes
    _ = result.write_text('{"patch_result": {"build_su')
    assert demo.grade(result, since=0) is None  # half written
    _ = result.write_text('{"runtime_result": {}}')
    assert demo.grade(result, since=0) is None  # not a grade


def test_describe_the_grade() -> None:
    passing = {
        "patch_result": {
            "build_success": True,
            "pov_passed": 1,
            "pov_total": 1,
            "func_test_success": True,
            "intent_test_success": False,
        }
    }

    assert demo.describe(passing) == ("build passed, PoC 1/1 passed, functional tests passed, intent tests failed")


def test_the_log_shows_progress_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    log = tmp_path / "demo.log"
    _ = log.write_text(
        "#5 [ 1/12] FROM docker.io/library/ubuntu\n"
        "INFO:ssebench.tasks.catalog:Pulling case image x...\n"
        'time=2026-09-29T22:26:22Z level=INFO service=ssebench msg="Evaluators complete."\n'
        "WARNING:ssebench.tasks.catalog:Cannot pull x\n"
        "INFO:root:Build"
    )
    tail = demo.LogTail(log)

    tail.show()

    out = capsys.readouterr().out
    assert out == "  Pulling case image x...\n  warning: Cannot pull x\n"

    # The unfinished last line is shown once it is complete.
    with log.open("a") as f:
        _ = f.write("ing case image y\n")
    tail.show()
    assert capsys.readouterr().out == "  Building case image y\n"


def test_ports_in_use_are_named(fake: FakeDocker, monkeypatch: pytest.MonkeyPatch) -> None:
    d = demo.configure()
    monkeypatch.setattr(demo, "port_free", lambda port: port != d.webui_port)

    with pytest.raises(demo.DemoError, match="SSEBENCH_DEMO_WEBUI_PORT"):
        demo.check_ports(d)


def test_ports_of_a_running_demo_are_not_checked(fake: FakeDocker, monkeypatch: pytest.MonkeyPatch) -> None:
    d = demo.configure()
    fake.listing[frozenset({demo.project_label(d), "status=running"})] = ["abc123"]
    monkeypatch.setattr(demo, "port_free", lambda port: False)

    demo.check_ports(d)


def test_an_agent_needs_a_model() -> None:
    with pytest.raises(demo.DemoError, match="--model is required"):
        _ = demo.up(demo.Plan(task=TASK, agent="claude-code", model=None, timeout=60, build=False))


def test_an_unknown_task_is_refused() -> None:
    with pytest.raises(demo.DemoError, match="not in the catalog"):
        _ = demo.up(demo.Plan(task="no-such-task", agent="reference", model=None, timeout=60, build=False))


MODELS = """\
- model_name: claude
  litellm_params:
    model: anthropic/claude
    api_key: os.environ/ANTHROPIC_API_KEY
- model_name: local
  litellm_params:
    model: ollama/local
"""


@pytest.fixture
def models_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "models").mkdir()
    _ = (tmp_path / "models" / "providers.yaml").write_text(MODELS)
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path))
    return tmp_path


def test_model_key_is_needed_in_dot_env(models_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "dotenv", dict)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "only-in-the-shell")

    check = doctor.check_model_key("claude")

    assert check.status is Status.FAIL
    assert "ANTHROPIC_API_KEY is not set in .env" in check.detail


def test_model_key_set_in_dot_env(models_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "dotenv", lambda: {"ANTHROPIC_API_KEY": "sk-ant"})

    assert doctor.check_model_key("claude").status is Status.OK


def test_model_without_a_key_and_unknown_model(models_home: Path) -> None:
    assert doctor.check_model_key("local").status is Status.OK

    unknown = doctor.check_model_key("gpt-nine")
    assert unknown.status is Status.FAIL
    assert "not defined" in unknown.detail


def test_without_a_checkout_results_go_to_the_workspace_and_builds_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(paths, "workspace", lambda: tmp_path)
    monkeypatch.setattr(paths, "is_packaged", lambda: True)
    d = demo.configure()
    pulled = demo.Plan(task=TASK, agent="reference", model=None, timeout=60, build=False, run_id="r1")
    built = demo.Plan(task=TASK, agent="reference", model=None, timeout=60, build=True)

    assert pulled.result_file == tmp_path / "results" / TASK / "none" / "reference" / "r1" / "result.json"
    assert "--catalog" in pulled.run_command(d)
    with pytest.raises(paths.HomeNotFoundError, match="needs an SSEBench checkout"):
        _ = built.run_command(d)
    with pytest.raises(paths.HomeNotFoundError, match="needs an SSEBench checkout"):
        demo.build_base("base-generic-go:1.0.0")


def test_the_run_starts_in_the_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    started: list[Any] = []

    class Popen:
        pid = 1

        def __init__(self, cmd: list[str], **kwargs: Any) -> None:
            started.append(kwargs["cwd"])

    monkeypatch.setattr(demo.subprocess, "Popen", Popen)
    monkeypatch.setattr(paths, "workspace", lambda: tmp_path)
    plan = demo.Plan(task=TASK, agent="reference", model=None, timeout=60, build=False)

    _, log = demo.start_run(demo.configure(), plan, None)

    assert started == [tmp_path]
    assert log.parent == tmp_path / "results"


def test_the_run_s_container_is_found_by_its_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[tuple[str, ...]] = []

    def container_ids(*filters: str) -> list[str]:
        asked.append(filters)
        return ["abc123"]

    monkeypatch.setattr(demo, "container_ids", container_ids)
    plan = demo.Plan(task=TASK, agent="reference", model=None, timeout=60, build=False, run_id="demo-run")

    assert demo.find_run(demo.configure(), plan) == "abc123"
    assert "label=ssebench.run-id=demo-run" in asked[0]


def test_the_web_ui_is_asked_for_the_run_by_its_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    urls: list[str] = []

    def get(url: str, timeout: float) -> httpx.Response:
        urls.append(url)
        return httpx.Response(200, json={"available": True})

    monkeypatch.setattr(demo.httpx, "get", get)
    config = demo.configure()

    demo.check_run_in_webui(config, "20260930-152335-e5fd25")

    assert urls == [f"{config.webui_url}/api/containers/20260930-152335-e5fd25/result"]


# ==================== the web UI's health ====================


def test_a_web_ui_that_reaches_its_runner_passes() -> None:
    # The shape of GET /api/health in webui/server/index.ts.
    assert demo.runner_problem({"status": "ok", "runner": True, "backend": "docker", "terminal": False}) is None


def test_a_web_ui_that_cannot_reach_docker_says_why() -> None:
    problem = demo.runner_problem({"status": "ok", "runner": False, "backend": None, "runnerError": "connect ENOENT"})

    assert problem is not None
    assert "/var/run/docker.sock" in problem
    assert problem.endswith("It reports: connect ENOENT")


@pytest.mark.parametrize("health", [None, [], "ok", {"status": "ok"}, {"docker": True}])
def test_an_answer_without_the_runner_field_is_a_problem(health: object) -> None:
    assert demo.runner_problem(health) is not None
