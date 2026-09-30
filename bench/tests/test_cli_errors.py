"""`ssebench run` reports a bad model, agent, agent.yaml or image build as one error line, never a traceback."""

import logging
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast, override

import httpx
import pytest

from ssebench import doctor, paths, settings, stack
from ssebench.agents import Agent, AgentError
from ssebench.agents.agent import load_agent_config
from ssebench.backends import DockerBackend, ImageRequest, Images, ImageUnavailableError, ProxyEndpoint
from ssebench.cli import cli, demo
from ssebench.models import Model, ModelError
from ssebench.pipe import DockerLayerMixin, ImageBuildError, build_pipe

TASK = "demo-1"
MODELS = "- model_name: alpha-1\n- model_name: alpha-2\n- model_name: beta\n"


@pytest.fixture(autouse=True)
def no_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Runs that fail validation must do so before the proxy starts; anything that starts it is a failure."""

    def start(*args: object, **kwargs: object) -> None:
        raise AssertionError("the LiteLLM proxy must not start")

    monkeypatch.setattr(stack, "up", start)
    monkeypatch.setattr(stack, "wait_healthy", start)


@pytest.fixture
def models_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "models"
    directory.mkdir()
    _ = (directory / "test.yaml").write_text(MODELS)
    monkeypatch.setattr(paths, "models_dir", lambda: directory)
    return directory


@pytest.fixture
def agents_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "agents"
    for name in ("dummy", "helper"):
        (directory / name).mkdir(parents=True)
        _ = (directory / name / "agent.yaml").write_text(f"name: {name}\n")
    monkeypatch.setattr(paths, "agents_dir", lambda: directory)
    return directory


@pytest.fixture
def dataset(tmp_path: Path, make_task: Callable[..., Path]) -> Path:
    directory = tmp_path / "pilot"
    _ = make_task(directory, TASK)
    return directory


def run_args(dataset: Path, *args: str) -> list[str]:
    return ["run", "--task", TASK, "--local", str(dataset), *args]


def run_cli(argv: list[str]) -> int:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(argv)
    return cast(int, exit_info.value.code)


def errors(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]


# ==================== --model ====================


def test_unknown_model_lists_the_valid_choices(
    dataset: Path, agents_dir: Path, models_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    assert run_cli(run_args(dataset, "--agent", "dummy", "--model", "gamma")) == 1

    assert errors(caplog) == ["Unknown model 'gamma'. Available models: alpha-1, alpha-2, beta."]


def test_unknown_model_suggests_the_closest_name(
    dataset: Path, agents_dir: Path, models_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    assert run_cli(run_args(dataset, "--agent", "dummy", "--model", "alpha1")) == 1

    [message] = errors(caplog)
    assert message.startswith("Unknown model 'alpha1' (did you mean 'alpha-1'?). Available models: ")


def test_a_reference_run_does_not_check_the_model_name(
    dataset: Path, agents_dir: Path, models_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (agents_dir / "reference").mkdir()
    _ = (agents_dir / "reference" / "agent.yaml").write_text("name: reference\n")
    reached: list[str] = []

    def start(*args: object, **kwargs: object) -> None:
        reached.append("proxy")
        raise subprocess.CalledProcessError(1, ["docker", "compose"])

    monkeypatch.setattr(stack, "up", start)
    monkeypatch.setattr("ssebench.cli.cli.reference_patch_path", lambda task: Path("patch.diff"))

    assert run_cli(run_args(dataset, "--agent", "reference", "--model", "gamma")) == 1
    assert reached == ["proxy"]


def model_with_proxy(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response], models_dir: Path
) -> None:
    real_client = httpx.Client
    monkeypatch.setattr(settings, "litellm_master_key", lambda: "master")
    monkeypatch.setattr(
        "ssebench.models.model.httpx.Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )


def test_a_model_the_proxy_does_not_serve_is_an_error_with_the_choices(
    monkeypatch: pytest.MonkeyPatch, models_dir: Path
) -> None:
    model_with_proxy(monkeypatch, lambda request: httpx.Response(404), models_dir)

    with pytest.raises(ModelError, match=r"does not serve model 'beta', although models/\*\.yaml define it"):
        _ = Model("beta")


def test_a_model_that_neither_the_proxy_nor_models_define_is_an_error_with_the_choices(
    monkeypatch: pytest.MonkeyPatch, models_dir: Path
) -> None:
    model_with_proxy(monkeypatch, lambda request: httpx.Response(404), models_dir)

    with pytest.raises(ModelError, match=r"Unknown model 'gamma'\. Available models: alpha-1, alpha-2, beta\."):
        _ = Model("gamma")


def test_a_model_uses_the_urls_of_a_backends_proxy(monkeypatch: pytest.MonkeyPatch, models_dir: Path) -> None:
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        body = {"user_id": "u", "key": "sk-run"} if request.method == "POST" else {}
        return httpx.Response(200, json=body, request=request)

    model_with_proxy(monkeypatch, handler, models_dir)

    model = Model("beta", ProxyEndpoint(host_url="http://proxy.test:4000", service_url="http://litellm.ns.svc:4000"))

    assert urls == ["http://proxy.test:4000/models/beta", "http://proxy.test:4000/user/new"]
    assert model.service_url == "http://litellm.ns.svc:4000" and model.api_key == "sk-run"


class ProxiedBackend(DockerBackend):
    """A backend with a proxy of its own; it cannot prepare images, which ends the run after the proxy is chosen."""

    @override
    def proxy(self) -> ProxyEndpoint:
        return ProxyEndpoint(host_url="http://proxy.test:4000", service_url="http://litellm.ns.svc:4000")

    @override
    def prepare_images(self, request: ImageRequest) -> Images:
        raise ImageUnavailableError("no images here")


def test_a_backend_with_its_own_proxy_starts_no_compose_stack(
    dataset: Path,
    agents_dir: Path,
    models_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("ssebench.cli.cli.resolve_backend", lambda name=None: ProxiedBackend())
    monkeypatch.chdir(tmp_path)
    proxies: list[ProxyEndpoint | None] = []
    monkeypatch.setattr("ssebench.cli.cli.Model", lambda name, proxy=None: proxies.append(proxy) or cast(Any, object()))
    # The stack must not start (see `no_proxy`), and the provider key is the proxy's business, not this host's.
    monkeypatch.setattr(doctor, "require_model_key", lambda model: pytest.fail("no provider key is checked here"))

    with pytest.raises(ImageUnavailableError, match="no images here"):
        _ = cli.cmd_run(cli.build_parser([])[0].parse_args(run_args(dataset, "--agent", "dummy", "--model", "beta")))

    assert proxies == [ProxyEndpoint(host_url="http://proxy.test:4000", service_url="http://litellm.ns.svc:4000")]


def test_a_proxy_that_rejects_the_key_is_an_error(monkeypatch: pytest.MonkeyPatch, models_dir: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200 if request.method == "GET" else 401, request=request)

    model_with_proxy(monkeypatch, handler, models_dir)

    with pytest.raises(ModelError, match=r"Cannot use the LiteLLM proxy at http://localhost:\d+: .*401"):
        _ = Model("beta")


def test_a_proxy_that_cannot_be_reached_is_an_error(monkeypatch: pytest.MonkeyPatch, models_dir: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    model_with_proxy(monkeypatch, handler, models_dir)

    with pytest.raises(ModelError, match="Cannot use the LiteLLM proxy .*connection refused"):
        _ = Model("beta")


def test_unknown_task_is_one_error_line(
    dataset: Path, agents_dir: Path, models_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    argv = ["run", "--task", "no-such-task", "--local", str(dataset), "--agent", "dummy", "--model", "beta"]

    assert run_cli(argv) == 1

    assert errors(caplog) == ["Benchmark task no-such-task does not exist."]


# ==================== the provider key ====================

KEYED_MODELS = "- model_name: keyed\n  litellm_params:\n    model: x/keyed\n    api_key: os.environ/OPENAI_API_KEY\n"


@pytest.fixture
def keyed_model(models_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A model that needs OPENAI_API_KEY, and an .env without it."""
    _ = (models_dir / "keyed.yaml").write_text(KEYED_MODELS)
    env = tmp_path / ".env"
    _ = env.write_text("LITELLM_MASTER_KEY=k\n")
    monkeypatch.setattr(paths, "env_file", lambda: env)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return env


def test_a_missing_provider_key_stops_the_run_before_anything_is_built(
    dataset: Path,
    agents_dir: Path,
    keyed_model: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("nothing may be built"))

    assert run_cli(run_args(dataset, "--agent", "helper", "--model", "keyed")) == 1

    assert errors(caplog) == [
        "Model 'keyed': OPENAI_API_KEY is not set in .env. "
        f"Put the key in {keyed_model}; the proxy reads provider keys only from there."
    ]


def test_a_key_set_only_in_the_shell_does_not_count(
    dataset: Path,
    agents_dir: Path,
    keyed_model: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-shell")

    assert run_cli(run_args(dataset, "--agent", "helper", "--model", "keyed")) == 1

    assert "OPENAI_API_KEY is not set in .env" in errors(caplog)[0]


def test_a_key_in_dot_env_lets_the_run_go_on(
    dataset: Path, agents_dir: Path, keyed_model: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = keyed_model.write_text("OPENAI_API_KEY=sk-file\n")
    reached: list[str] = []

    def start(*args: object, **kwargs: object) -> None:
        reached.append("proxy")
        raise subprocess.CalledProcessError(1, ["docker", "compose"])

    monkeypatch.setattr(stack, "up", start)

    assert run_cli(run_args(dataset, "--agent", "helper", "--model", "keyed")) == 1
    assert reached == ["proxy"]


@pytest.mark.parametrize("agent", ["dummy", "reference"])
def test_the_agents_that_make_no_model_calls_need_no_key(
    agent: str, dataset: Path, agents_dir: Path, keyed_model: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (agents_dir / "reference").mkdir(exist_ok=True)
    _ = (agents_dir / "reference" / "agent.yaml").write_text("name: reference\n")
    monkeypatch.setattr("ssebench.cli.cli.reference_patch_path", lambda task: Path("patch.diff"))
    reached: list[str] = []

    def start(*args: object, **kwargs: object) -> None:
        reached.append("proxy")
        raise subprocess.CalledProcessError(1, ["docker", "compose"])

    monkeypatch.setattr(stack, "up", start)

    assert run_cli(run_args(dataset, "--agent", agent, "--model", "keyed")) == 1
    assert reached == ["proxy"]


# ==================== --agent ====================


def test_unknown_agent_lists_the_valid_choices(
    dataset: Path, agents_dir: Path, models_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    assert run_cli(run_args(dataset, "--agent", "nothing", "--model", "beta")) == 1

    assert errors(caplog) == ["Unknown agent 'nothing'. Available agents: dummy, helper."]


def test_unknown_agent_suggests_the_closest_name(
    dataset: Path, agents_dir: Path, models_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    assert run_cli(run_args(dataset, "--agent", "dumy", "--model", "beta")) == 1

    assert errors(caplog) == ["Unknown agent 'dumy' (did you mean 'dummy'?). Available agents: dummy, helper."]


@pytest.mark.parametrize("name", ["", "..", "dummy/..", "../agents/dummy"])
def test_an_agent_name_cannot_leave_the_agents_folder(
    name: str, dataset: Path, agents_dir: Path, models_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    assert run_cli(run_args(dataset, "--agent", name, "--model", "beta")) == 1

    [message] = errors(caplog)
    assert message.startswith(f"Unknown agent {name!r}")
    assert message.endswith("Available agents: dummy, helper.")


# ==================== agent.yaml ====================


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("version: 1.0\n", r"agent\.yaml is not a valid agent config: name: Field required"),
        ("name: dummy\nmodel: x\n", r"is not a valid agent config: model: Extra inputs are not permitted"),
        ("name: '  '\n", r"is not a valid agent config: name: Value error, Name must be a non-empty string"),
        ("", r"is not a valid agent config: the file: Input should be a valid dictionary"),
        ("- just\n- a list\n", r"is not a valid agent config: the file: Input should be a valid dictionary"),
        (
            "name: [unclosed\n",
            r"agent\.yaml is not valid YAML: expected ',' or ']', but got '<stream end>' \(line 2\)$",
        ),
    ],
)
def test_a_bad_agent_yaml_is_one_error_line(
    content: str,
    expected: str,
    dataset: Path,
    agents_dir: Path,
    models_dir: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _ = (agents_dir / "dummy" / "agent.yaml").write_text(content)

    assert run_cli(run_args(dataset, "--agent", "dummy", "--model", "beta")) == 1

    [message] = errors(caplog)
    assert "\n" not in message
    assert message.startswith(str(agents_dir / "dummy" / "agent.yaml"))
    assert re.search(expected, message)


def test_an_agent_folder_without_agent_yaml_is_an_error(
    dataset: Path, agents_dir: Path, models_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (agents_dir / "bare").mkdir()

    assert run_cli(run_args(dataset, "--agent", "bare", "--model", "beta")) == 1

    assert errors(caplog) == [
        f"{agents_dir / 'bare' / 'agent.yaml'} does not exist; an agent folder needs an agent.yaml"
    ]


def test_load_agent_config_raises_agent_errors(tmp_path: Path) -> None:
    with pytest.raises(AgentError, match="does not exist"):
        _ = load_agent_config(tmp_path / "missing.yaml")


# ==================== a failed image build ====================


class Layer(DockerLayerMixin):
    def __init__(self, failure: BaseException | None = None) -> None:
        self.failure = failure

    @override
    def docker_image(self, base: str | None) -> str:
        if self.failure is not None:
            raise self.failure
        return "image"

    @override
    def describe(self) -> str:
        return "test image"


def test_build_pipe_reports_a_failed_docker_build() -> None:
    failure = subprocess.CalledProcessError(3, ["docker", "buildx", "build", "--build-context", "a=b", "-t", "x"])

    with pytest.raises(ImageBuildError) as error:
        _ = build_pipe([Layer(), Layer(failure)])

    assert str(error.value) == (
        "Building the test image failed: `docker buildx build` exited with status 3 (its output is above)"
    )


def test_build_pipe_reports_a_missing_docker() -> None:
    with pytest.raises(ImageBuildError, match=r"Building the test image failed: .*docker"):
        _ = build_pipe([Layer(FileNotFoundError(2, "No such file or directory", "docker"))])


def test_a_failed_agent_image_build_is_one_error_line(
    dataset: Path,
    agents_dir: Path,
    models_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(stack, "up", lambda *args, **kwargs: None)
    monkeypatch.setattr(stack, "wait_healthy", lambda *args, **kwargs: None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("ssebench.cli.cli.Model", lambda name, proxy=None: cast(Any, object()))

    def docker(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if kwargs.get("cwd") == agents_dir / "dummy":
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", docker)

    assert run_cli(run_args(dataset, "--agent", "dummy", "--model", "beta")) == 1

    assert errors(caplog) == [
        "Building the image of agent 'dummy' failed: `docker buildx build` exited with status 1 (its output is above)"
    ]


def test_a_failed_case_image_build_names_the_task(
    dataset: Path,
    agents_dir: Path,
    models_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(stack, "up", lambda *args, **kwargs: None)
    monkeypatch.setattr(stack, "wait_healthy", lambda *args, **kwargs: None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("ssebench.cli.cli.Model", lambda name, proxy=None: cast(Any, object()))

    def docker(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(subprocess, "run", docker)

    assert run_cli(run_args(dataset, "--agent", "dummy", "--model", "beta")) == 1

    assert errors(caplog) == [
        f"Building the case image of task {TASK} failed: `docker buildx build` exited with status 1 (its output is above)"
    ]


def test_ctrl_c_ends_the_command_with_one_line(
    dataset: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def interrupted(args: object) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "cmd_run", interrupted)

    assert run_cli(run_args(dataset, "--agent", "dummy", "--model", "beta")) == 130
    assert errors(caplog) == ["Interrupted"]


# ==================== the demo ====================


def test_the_demo_reports_an_unknown_agent_as_an_error(agents_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    def action() -> int:
        _ = Agent("nothing")
        return 0

    assert demo.guarded(action) == 1
    assert errors(caplog) == ["Unknown agent 'nothing'. Available agents: dummy, helper."]


# ==================== no traceback ====================


def test_the_command_line_prints_no_traceback(dataset: Path, tmp_path: Path) -> None:
    bad_agent = subprocess.run(
        [sys.executable, "-m", "ssebench", *run_args(dataset, "--agent", "no-such-agent", "--model", "no-such-model")],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )
    bad_model = subprocess.run(
        [sys.executable, "-m", "ssebench", *run_args(dataset, "--agent", "dummy", "--model", "no-such-model")],
        capture_output=True,
        text=True,
        cwd=tmp_path,
    )

    for result, needle in ((bad_agent, "Unknown agent"), (bad_model, "Unknown model")):
        assert result.returncode == 1
        assert "Traceback" not in result.stderr
        assert needle in result.stderr
        assert len(result.stderr.strip().splitlines()) == 1


# ==================== proxy ====================


def test_proxy_up_reports_a_proxy_that_exited(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def exited(*args: object, **kwargs: object) -> None:
        raise stack.ProxyError("The LiteLLM proxy container exited before it became healthy")

    monkeypatch.setattr(stack, "up", lambda *args, **kwargs: None)
    monkeypatch.setattr(stack, "wait_healthy", exited)

    assert run_cli(["proxy", "up"]) == 1
    assert errors(caplog) == ["The LiteLLM proxy container exited before it became healthy"]


@pytest.mark.parametrize(("argv", "volumes"), [(["proxy", "down"], False), (["proxy", "down", "--volumes"], True)])
def test_proxy_down_removes_the_volume_only_when_asked(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], volumes: bool
) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(stack, "down", lambda volumes=False: calls.append(volumes))

    assert run_cli(argv) == 0
    assert calls == [volumes]
