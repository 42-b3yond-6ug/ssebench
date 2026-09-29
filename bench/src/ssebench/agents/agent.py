import os
import subprocess
from pathlib import Path
from typing import ClassVar, final, override

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ssebench import paths
from ssebench.pipe import REGISTRY, TAG, DockerLayerMixin


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


def get_agent_path(name: str) -> Path:
    agents_dir = paths.agents_dir()
    if os.path.exists(agents_dir / name):
        return agents_dir / name
    else:
        raise FileNotFoundError(f"Agent {name} does not exist.")


def load_agent_config(config_path: Path) -> AgentConfig:
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file {config_path} does not exist.")

    with open(config_path) as file:
        return AgentConfig.model_validate(yaml.safe_load(file))


@final
class Agent(DockerLayerMixin):
    def __init__(self, name: str, task_name: str | None = None):
        agent_path = get_agent_path(name)
        agent_config = load_agent_config(agent_path / "agent.yaml")

        self.agent_name = name
        self.agent_path = agent_path
        self.agent_config = agent_config
        self.task_name = task_name or "any"

    @override
    def docker_image(self, base: str | None) -> str:
        if base is None:
            raise RuntimeError("Agent layer requires a base image")

        docker_image_name = (
            f"{REGISTRY}/agent-{self.agent_config.name}/{self.task_name}:{self.agent_config.version}"
        ).lower()

        subprocess.run(
            [
                "docker",
                "buildx",
                "build",
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
