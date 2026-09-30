import json
import shutil
from collections import namedtuple
from pathlib import Path

import httpx
import pytest

from ssebench import arch, doctor, paths, stack
from ssebench.doctor import Status

VARIABLES = (
    "LITELLM_MASTER_KEY",
    "POSTGRES_PASSWORD",
    "LITELLM_PORT",
    "COMPOSE_PROJECT_NAME",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
)
Usage = namedtuple("Usage", "total used free")
MODELS = """\
- model_name: claude
  litellm_params:
    model: anthropic/claude
    api_key: os.environ/ANTHROPIC_API_KEY
- model_name: gpt
  litellm_params:
    model: openai/gpt
    api_key: os.environ/OPENAI_API_KEY
- model_name: local
  litellm_params:
    model: ollama/local
"""
SECRETS = "LITELLM_MASTER_KEY=sk-test\nPOSTGRES_PASSWORD=pw\n"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _ = (tmp_path / "pyproject.toml").write_text("[tool.ssebench]\n")
    (tmp_path / "models").mkdir()
    _ = (tmp_path / "models" / "providers.yaml").write_text(MODELS)
    monkeypatch.setenv(paths.HOME_ENV, str(tmp_path))
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    return tmp_path


@pytest.fixture
def healthy_host(home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A host where every probe succeeds."""
    outputs = {
        ("docker", "version"): "29.0.0",
        ("docker", "buildx"): "github.com/docker/buildx v0.30.0 abcdef",
        ("docker", "compose"): "2.40.0",
        ("docker", "info"): str(home),
    }
    monkeypatch.setattr(doctor, "run", lambda cmd: (0, outputs[tuple(cmd[:2])]))
    monkeypatch.setattr(shutil, "disk_usage", lambda _: Usage(0, 0, 500 * doctor.GIB))
    monkeypatch.setattr(arch.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(stack, "is_healthy", lambda: True)
    _ = (home / ".env").write_text(SECRETS + "ANTHROPIC_API_KEY=a\nOPENAI_API_KEY=o\n")
    return home


def by_name(checks: list[doctor.Check]) -> dict[str, doctor.Check]:
    return {check.name: check for check in checks}


def test_everything_ok(healthy_host: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert doctor.main() == 0
    out = capsys.readouterr().out
    assert "fail" not in out
    assert "All required checks passed (0 warning(s))" in out


def test_docker_unreachable_is_a_failure(healthy_host: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def run(cmd: list[str]) -> tuple[int, str]:
        if cmd[:2] == ["docker", "version"]:
            return 1, "Cannot connect to the Docker daemon at unix:///var/run/docker.sock."
        return 0, "ok"

    monkeypatch.setattr(doctor, "run", run)

    check = by_name(doctor.run_checks())["Docker"]
    assert check.status is Status.FAIL
    assert "Cannot connect" in check.detail
    assert "docker info" in check.fix
    assert doctor.main() == 1


def test_missing_buildx_is_a_failure(healthy_host: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        doctor, "run", lambda cmd: (1, "unknown command: docker buildx") if "buildx" in cmd else (0, "1")
    )

    assert doctor.check_buildx().status is Status.FAIL


@pytest.mark.parametrize(("free_gib", "status"), [(5, Status.FAIL), (30, Status.WARN), (200, Status.OK)])
def test_disk_thresholds(healthy_host: Path, monkeypatch: pytest.MonkeyPatch, free_gib: int, status: Status) -> None:
    monkeypatch.setattr(shutil, "disk_usage", lambda _: Usage(0, 0, free_gib * doctor.GIB))

    assert doctor.check_disk(healthy_host).status is status


def test_disk_falls_back_to_the_home(healthy_host: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def disk_usage(path: Path) -> Usage:
        if Path(path) != healthy_host:
            raise PermissionError(path)
        return Usage(0, 0, 100 * doctor.GIB)

    monkeypatch.setattr(doctor, "run", lambda cmd: (0, "/var/lib/docker"))
    monkeypatch.setattr(shutil, "disk_usage", disk_usage)

    check = doctor.check_disk(healthy_host)
    assert check.status is Status.OK
    assert str(healthy_host) in check.detail


@pytest.mark.parametrize("machine", ["x86_64", "AMD64"])
def test_amd64_is_ok(healthy_host: Path, monkeypatch: pytest.MonkeyPatch, machine: str) -> None:
    monkeypatch.setattr(arch.platform, "machine", lambda: machine)

    check = doctor.check_cpu()
    assert check.status is Status.OK
    assert check.detail == machine.lower()


@pytest.mark.parametrize("machine", ["arm64", "aarch64", "riscv64"])
def test_non_amd64_warns_that_tasks_run_under_emulation(
    healthy_host: Path, monkeypatch: pytest.MonkeyPatch, machine: str
) -> None:
    monkeypatch.setattr(arch.platform, "machine", lambda: machine)

    check = doctor.check_cpu()
    assert check.status is Status.WARN
    assert machine in check.detail
    assert "amd64 emulation" in check.detail
    assert "slow" in check.detail
    assert "AddressSanitizer" in check.detail
    assert "binfmt" in check.fix


def test_the_warning_does_not_fail_the_check(
    healthy_host: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(arch.platform, "machine", lambda: "aarch64")

    assert doctor.main() == 0
    out = capsys.readouterr().out
    assert "warn  CPU" in out
    assert "All required checks passed (1 warning(s))" in out


def test_missing_env_file_fails_with_setup_hint(home: Path) -> None:
    check = doctor.check_env_file()

    assert check.status is Status.FAIL
    assert "just setup" in check.fix


def test_env_file_without_secrets_fails(home: Path) -> None:
    _ = (home / ".env").write_text("POSTGRES_PASSWORD=pw\n")

    check = doctor.check_env_file()
    assert check.status is Status.FAIL
    assert "LITELLM_MASTER_KEY" in check.detail


def test_secrets_from_the_environment_only_warn(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LITELLM_MASTER_KEY", "sk-test")
    monkeypatch.setenv("POSTGRES_PASSWORD", "pw")

    assert doctor.check_env_file().status is Status.WARN


def test_proxy_down_warns_with_the_configured_port(healthy_host: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stack, "is_healthy", lambda: False)
    monkeypatch.setenv("LITELLM_PORT", "4100")

    check = doctor.check_proxy()
    assert check.status is Status.WARN
    assert "http://localhost:4100/health/liveliness" in check.detail
    assert "just launch" in check.fix


def test_bad_port_fails(healthy_host: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LITELLM_PORT", "http")

    assert doctor.check_proxy().status is Status.FAIL


def test_provider_keys_are_read_from_models(home: Path) -> None:
    _ = (home / "models" / "broken.yaml").write_text("- model_name: [unclosed\n")

    assert doctor.provider_keys() == {"ANTHROPIC_API_KEY": ["claude"], "OPENAI_API_KEY": ["gpt"]}


def test_provider_keys_report_missing_and_shell_only(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = (home / ".env").write_text(SECRETS + "ANTHROPIC_API_KEY=\n")
    monkeypatch.setenv("OPENAI_API_KEY", "from-shell")

    check = doctor.check_provider_keys()
    assert check.status is Status.WARN
    assert "missing: ANTHROPIC_API_KEY (1 model)" in check.detail
    assert "only in your shell, not in .env: OPENAI_API_KEY" in check.detail


def test_missing_provider_keys_do_not_fail(healthy_host: Path) -> None:
    _ = (healthy_host / ".env").write_text(SECRETS)

    assert doctor.main() == 0


def test_render_prints_fixes_for_problems_only() -> None:
    text = doctor.render(
        [
            doctor.Check("Docker", Status.OK, "daemon 29", "never shown"),
            doctor.Check("CPU", Status.WARN, "arm64", "use x86-64"),
        ]
    )

    assert "never shown" not in text
    assert "fix: use x86-64" in text
    assert text.endswith("All required checks passed (1 warning(s)).")


def test_model_keys_lists_the_keys_each_model_needs_and_lacks(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = (home / ".env").write_text(SECRETS + "ANTHROPIC_API_KEY=a\n")
    monkeypatch.setenv("OPENAI_API_KEY", "from-shell")

    assert doctor.model_keys() == {
        "claude": {"keys": ["ANTHROPIC_API_KEY"], "missing": []},
        "gpt": {"keys": ["OPENAI_API_KEY"], "missing": ["OPENAI_API_KEY"]},
        "local": {"keys": [], "missing": []},
    }


def test_json_output_has_the_checks_and_the_models(healthy_host: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _ = (healthy_host / ".env").write_text(SECRETS + "ANTHROPIC_API_KEY=a\n")

    assert doctor.main(as_json=True) == 0

    data = json.loads(capsys.readouterr().out)
    assert {"name": "Docker", "status": "ok", "detail": "daemon 29.0.0", "fix": ""} in data["checks"]
    assert data["models"]["gpt"] == {"keys": ["OPENAI_API_KEY"], "missing": ["OPENAI_API_KEY"]}


def provider(status: int, seen: list[httpx.Request] | None = None) -> httpx.Client:
    """A client whose every request is answered with `status`, and recorded in `seen`."""

    def answer(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, json={"data": []})

    return httpx.Client(transport=httpx.MockTransport(answer))


def test_keys_are_not_sent_to_providers_unless_asked(healthy_host: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: pytest.fail("no request may be made"))

    assert not [check for check in doctor.run_checks() if check.name.startswith("Provider key ")]


def test_a_key_the_provider_accepts_is_ok(healthy_host: Path) -> None:
    seen: list[httpx.Request] = []

    [anthropic, openai] = doctor.check_provider_key_values(provider(200, seen))

    assert (anthropic.name, anthropic.status) == ("Provider key ANTHROPIC_API_KEY", Status.OK)
    assert (openai.name, openai.status) == ("Provider key OPENAI_API_KEY", Status.OK)
    # The model-list endpoints, which are free, and the key in the header each provider reads.
    assert [(r.method, r.url.host, r.url.path) for r in seen] == [
        ("GET", "api.anthropic.com", "/v1/models"),
        ("GET", "api.openai.com", "/v1/models"),
    ]
    assert seen[0].headers["x-api-key"] == "a" and seen[1].headers["authorization"] == "Bearer o"


@pytest.mark.parametrize("status", [401, 403])
def test_a_rejected_key_is_a_warning_with_a_fix(healthy_host: Path, status: int) -> None:
    check = doctor.check_key_accepted("ANTHROPIC_API_KEY", "a", provider(status))

    assert check.status is Status.WARN
    assert f"HTTP {status}" in check.detail and "api.anthropic.com" in check.detail
    assert "ANTHROPIC_API_KEY" in check.fix


def test_a_provider_that_errors_leaves_the_key_unverified(healthy_host: Path) -> None:
    check = doctor.check_key_accepted("OPENAI_API_KEY", "o", provider(503))

    assert check.status is Status.WARN and "not verified" in check.detail


def test_a_provider_that_cannot_be_reached_is_a_warning(healthy_host: Path) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    check = doctor.check_key_accepted("OPENAI_API_KEY", "o", httpx.Client(transport=httpx.MockTransport(refuse)))

    assert check.status is Status.WARN and "could not ask api.openai.com" in check.detail


def test_only_the_keys_that_env_sets_are_tried(healthy_host: Path) -> None:
    _ = (healthy_host / ".env").write_text(SECRETS + "OPENAI_API_KEY=o\n")

    [openai] = doctor.check_provider_key_values(provider(200))

    assert openai.name == "Provider key OPENAI_API_KEY"


def test_verify_keys_adds_the_checks_to_the_report(
    healthy_host: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        doctor, "check_provider_key_values", lambda: [doctor.Check("Provider key X", Status.WARN, "bad")]
    )

    assert doctor.main(verify_keys=True) == 0
    assert "Provider key X" in capsys.readouterr().out
