import difflib
import subprocess
from pathlib import Path
from typing import ClassVar, final, override

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ssebench import paths
from ssebench.arch import platform_args
from ssebench.errors import UserError
from ssebench.pipe import REGISTRY, TAG, DockerLayerMixin


class AgentError(UserError):
    """The agent is unknown, or its `agent.yaml` is missing or invalid."""


class AgentConfig(BaseModel):
    """An agent's `agent.yaml`, next to its Dockerfile in `agents/<agent>/`."""

    # Forbid extra / unknown keys from YAML
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", title="SSEBench agent config")

    # Agent Config Fields
    name: str = Field(description="Name of the agent, used in the names of its images.")
    # A factory keeps the release version out of the JSON Schema, which documents this file.
    version: str = Field(
        default_factory=lambda: TAG, description="Tag of the agent image; the SSEBench version when it is not set."
    )

    # Validators
    @field_validator("name")
    @classmethod
    def name_non_empty(cls, v: str):
        if not v or not v.strip():
            raise ValueError("Name must be a non-empty string.")
        return v.strip()


def available_agents() -> list[str]:
    """The agents under `agents/`: the folders with an `agent.yaml`."""
    return sorted(p.parent.name for p in paths.agents_dir().glob("*/agent.yaml"))


def get_agent_path(name: str) -> Path:
    """The folder of the agent called `name`.

    Raises:
        AgentError: If there is no such agent. The message lists the agents there are.
    """
    agents_dir = paths.agents_dir()
    folders = {p.name for p in agents_dir.iterdir() if p.is_dir()} if agents_dir.is_dir() else set()
    if name not in folders:
        message = f"Unknown agent {name!r}"
        if close := difflib.get_close_matches(name, available_agents(), n=1):
            message += f" (did you mean {close[0]!r}?)"
        raise AgentError(f"{message}. Available agents: {', '.join(available_agents())}.")
    return agents_dir / name


def load_agent_config(config_path: Path) -> AgentConfig:
    """Read and validate an `agent.yaml`.

    Raises:
        AgentError: If the file is missing, is not YAML or does not match `AgentConfig`.
    """
    try:
        data = yaml.safe_load(config_path.read_text())
    except FileNotFoundError:
        raise AgentError(f"{config_path} does not exist; an agent folder needs an agent.yaml") from None
    except OSError as e:
        raise AgentError(f"Cannot read {config_path}: {e}") from e
    except yaml.YAMLError as e:
        detail = str(e)
        if isinstance(e, yaml.MarkedYAMLError) and e.problem and e.problem_mark:
            detail = f"{e.problem} (line {e.problem_mark.line + 1})"
        raise AgentError(f"{config_path} is not valid YAML: {' '.join(detail.split())}") from e
    try:
        return AgentConfig.model_validate(data)
    except ValidationError as e:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or 'the file'}: {error['msg']}" for error in e.errors()
        )
        raise AgentError(f"{config_path} is not a valid agent config: {problems}") from e


@final
class Agent(DockerLayerMixin):
    """An agent's image, built on the image of the layer below it.

    `platform` (`linux/<arch>`) must be the platform of that image; None builds for the Docker host's own.
    """

    def __init__(self, name: str, task_name: str | None = None, platform: str | None = None):
        agent_path = get_agent_path(name)
        agent_config = load_agent_config(agent_path / "agent.yaml")

        self.agent_name = name
        self.agent_path = agent_path
        self.agent_config = agent_config
        self.task_name = task_name or "any"
        self.platform = platform

    @override
    def describe(self) -> str:
        return f"image of agent {self.agent_name!r}"

    @property
    def image_name(self) -> str:
        """The name of the agent image: `agent-<agent>/<task>:<version>` under the registry, lowercase.

        `<task>` is the task ID in sandbox mode and `sidecar` in sidecar mode, where every task shares the image.
        """
        return f"{REGISTRY}/agent-{self.agent_config.name}/{self.task_name}:{self.agent_config.version}".lower()

    @override
    def docker_image(self, base: str | None) -> str:
        if base is None:
            raise RuntimeError("Agent layer requires a base image")

        docker_image_name = self.image_name

        subprocess.run(
            [
                "docker",
                "buildx",
                "build",
                *platform_args(self.platform),
                "--build-context",
                f"ssebench-agent=docker-image://{base}",
                # In-repo agent wrappers are uv workspace members and install from the workspace root.
                "--build-context",
                f"workspace={paths.home()}",
                "-t",
                docker_image_name,
                "--load",
                ".",
            ],
            cwd=self.agent_path,
            check=True,
        )
        return docker_image_name
