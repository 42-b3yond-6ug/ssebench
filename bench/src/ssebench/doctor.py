"""`ssebench doctor`: check that this host can build images and run benchmarks, and say how to fix it."""

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import yaml

from ssebench import paths, settings, stack
from ssebench.models import model_names

GIB = 1024**3
# Case images of C tasks with their toolchains run to several GiB each.
DISK_FAIL_GIB = 10
DISK_WARN_GIB = 50
AMD64 = ("x86_64", "amd64")


class Status(Enum):
    OK = "ok"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    detail: str
    fix: str = ""


def run(cmd: list[str]) -> tuple[int, str]:
    """Run a probe command; return its exit code and its output (stdout, or stderr when empty)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)
    return result.returncode, result.stdout.strip() or result.stderr.strip()


def first_line(text: str) -> str:
    return text.splitlines()[0] if text else ""


def check_docker() -> Check:
    code, out = run(["docker", "version", "--format", "{{.Server.Version}}"])
    if code == 0:
        return Check("Docker", Status.OK, f"daemon {out}")
    return Check(
        "Docker",
        Status.FAIL,
        first_line(out) or "docker not found",
        "Install Docker, start the daemon, and make sure your user can reach it (`docker info`).",
    )


def check_buildx() -> Check:
    code, out = run(["docker", "buildx", "version"])
    if code == 0:
        fields = out.split()
        return Check("buildx", Status.OK, fields[1] if len(fields) > 1 else out)
    return Check(
        "buildx",
        Status.FAIL,
        first_line(out) or "docker buildx not found",
        "Install the Docker buildx plugin; SSEBench builds every image with `docker buildx build`.",
    )


def check_compose() -> Check:
    code, out = run(["docker", "compose", "version", "--short"])
    if code == 0:
        return Check("Compose", Status.OK, out)
    return Check(
        "Compose",
        Status.FAIL,
        first_line(out) or "docker compose not found",
        "Install the Docker Compose plugin; the LiteLLM proxy runs as a Compose stack.",
    )


def check_disk(home: Path) -> Check:
    # Images live under Docker's data root, which may be on another file system than the checkout.
    code, root = run(["docker", "info", "--format", "{{.DockerRootDir}}"])
    candidates = [Path(root)] if code == 0 and root else []
    candidates.append(home)
    for where in candidates:
        try:
            free = shutil.disk_usage(where).free / GIB
        except OSError:
            continue
        detail = f"{free:.0f} GiB free on {where}"
        fix = "Free up disk space; `docker system df` shows what Docker uses and `just case-clean` removes case images."
        if free < DISK_FAIL_GIB:
            return Check("Disk", Status.FAIL, detail, fix)
        if free < DISK_WARN_GIB:
            return Check("Disk", Status.WARN, f"{detail}; the pilot images need tens of GiB", fix)
        return Check("Disk", Status.OK, detail)
    return Check(
        "Disk", Status.WARN, "could not read the free space", "Check that the disk holding Docker's data has room."
    )


def check_cpu() -> Check:
    machine = platform.machine().lower()
    if machine in AMD64:
        return Check("CPU", Status.OK, machine)
    return Check(
        "CPU",
        Status.WARN,
        f"{machine or 'unknown'}: many pilot tasks build amd64-only images",
        "Use an x86-64 host, or expect some tasks to fail or to run slowly under emulation.",
    )


def check_env_file() -> Check:
    path = paths.env_file()
    missing = [name for name in stack.REQUIRED_SECRETS if not settings.get(name)]
    if path.is_file():
        if missing:
            return Check(
                ".env",
                Status.FAIL,
                f"{path} does not set {', '.join(missing)}",
                "Add them, or move .env aside and run `ssebench init` (`just setup` in a checkout) to write a new one.",
            )
        return Check(".env", Status.OK, str(path))
    if missing:
        return Check(".env", Status.FAIL, f"{path} not found", "Run `ssebench init` (`just setup` in a checkout).")
    return Check(
        ".env",
        Status.WARN,
        f"{path} not found; the proxy secrets come from the environment",
        "Run `ssebench init` (`just setup` in a checkout): the proxy reads provider keys only from .env.",
    )


def check_proxy() -> Check:
    try:
        url = stack.host_url()
    except settings.SettingError as e:
        return Check("LiteLLM", Status.FAIL, str(e), "Set LITELLM_PORT in .env to a free TCP port.")
    project = settings.compose_project()
    if stack.is_healthy():
        return Check("LiteLLM", Status.OK, f"healthy at {url} (Compose project {project})")
    return Check(
        "LiteLLM",
        Status.WARN,
        f"no answer at {stack.health_url()} (Compose project {project})",
        "`ssebench run` starts the proxy when needed; start it now with `ssebench proxy up` (`just launch` in a checkout). "
        f"If another program uses port {settings.litellm_port()}, set LITELLM_PORT in .env.",
    )


def provider_keys() -> dict[str, list[str]]:
    """The variables that `models/*.yaml` read with `os.environ/`, each with the models that use it."""
    refs: dict[str, list[str]] = {}
    for path in sorted(paths.models_dir().glob("*.y*ml")):
        try:
            entries = yaml.safe_load(path.read_text())
        except yaml.YAMLError:
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            params = entry.get("litellm_params") if isinstance(entry, dict) else None
            if not isinstance(params, dict):
                continue
            for value in params.values():
                if isinstance(value, str) and value.startswith("os.environ/"):
                    name = value.removeprefix("os.environ/")
                    refs.setdefault(name, []).append(str(entry.get("model_name", "?")))
    return refs


def check_provider_keys() -> Check:
    refs = provider_keys()
    if not refs:
        return Check("Provider keys", Status.OK, "no model in models/ needs a key")
    in_file = settings.dotenv()
    configured = sorted(name for name in refs if in_file.get(name, "").strip())
    shell_only = sorted(name for name in refs if name not in configured and os.environ.get(name, "").strip())
    missing = sorted(name for name in refs if name not in configured and name not in shell_only)

    def describe(names: list[str]) -> str:
        return ", ".join(f"{name} ({len(refs[name])} model{'s' if len(refs[name]) != 1 else ''})" for name in names)

    parts = []
    if configured:
        parts.append(f"set: {describe(configured)}")
    if shell_only:
        parts.append(f"only in your shell, not in .env: {describe(shell_only)}")
    if missing:
        parts.append(f"missing: {describe(missing)}")
    if not shell_only and not missing:
        return Check("Provider keys", Status.OK, "; ".join(parts))
    return Check(
        "Provider keys",
        Status.WARN,
        "; ".join(parts),
        "Put the key of each provider you use in .env (the proxy reads keys only from there), "
        "then restart the proxy with `ssebench proxy up`. The dummy and reference agents need no key.",
    )


def check_model_key(model: str) -> Check:
    """Whether `.env` holds the provider key that `model` needs. A key set only in the shell does not
    count: the proxy container reads its keys from `.env`."""
    name = f"Key for {model}"
    if model not in model_names():
        return Check(
            name,
            Status.FAIL,
            f"{model} is not defined in models/*.yaml",
            "Use a model name from models/*.yaml.",
        )
    needed = sorted(var for var, models in provider_keys().items() if model in models)
    in_file = settings.dotenv()
    missing = [var for var in needed if not in_file.get(var, "").strip()]
    if not missing:
        return Check(name, Status.OK, f"{', '.join(needed)} set in .env" if needed else "no key needed")
    return Check(
        name,
        Status.FAIL,
        f"{', '.join(missing)} is not set in .env",
        f"Put the key in {paths.env_file()}; the proxy reads provider keys only from there.",
    )


def host_checks() -> list[Check]:
    """What every run needs from this host: Docker, buildx, Compose, the CPU, disk space and `.env`."""
    return [
        check_docker(),
        check_buildx(),
        check_compose(),
        check_cpu(),
        check_disk(paths.workspace()),
        check_env_file(),
    ]


def run_checks() -> list[Check]:
    checks = [check_docker(), check_buildx(), check_compose(), check_cpu()]
    try:
        home = paths.home()
    except paths.HomeNotFoundError as e:
        checks.append(Check("SSEBench home", Status.FAIL, str(e), "Run from inside an SSEBench checkout."))
        return checks
    if paths.is_packaged():
        home_check = Check(
            "SSEBench home", Status.OK, f"{home} (packaged with ssebench, no checkout); workspace {paths.workspace()}"
        )
    else:
        home_check = Check("SSEBench home", Status.OK, str(home))
    return [home_check, *checks, check_disk(paths.workspace()), check_env_file(), check_proxy(), check_provider_keys()]


def render(checks: list[Check]) -> str:
    width = max(len(check.name) for check in checks)
    lines = []
    for check in checks:
        lines.append(f"  {check.status.value:<5} {check.name:<{width}}  {check.detail}")
        if check.fix and check.status is not Status.OK:
            lines.append(f"  {'':<5} {'':<{width}}  fix: {check.fix}")
    failures = sum(check.status is Status.FAIL for check in checks)
    warnings = sum(check.status is Status.WARN for check in checks)
    lines.append("")
    if failures:
        lines.append(f"{failures} required check(s) failed; fix them before running benchmarks.")
    else:
        lines.append(f"All required checks passed ({warnings} warning(s)).")
    return "\n".join(lines)


def main() -> int:
    checks = run_checks()
    print(render(checks))
    return 1 if any(check.status is Status.FAIL for check in checks) else 0
