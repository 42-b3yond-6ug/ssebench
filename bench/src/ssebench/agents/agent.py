import os
import subprocess
from pathlib import Path
from typing import ClassVar, final, override

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

from ssebench.pipe import REGISTRY, DockerLayerMixin


class AgentConfig(BaseModel):
    # Forbid extra / unknown keys from YAML
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    # Agent Config Fields
    name: str
    version: str = "latest"  # Default version is "latest"

    # Validators
    @field_validator("name")
    @classmethod
    def name_non_empty(cls, v: str):
        if not v or not v.strip():
            raise ValueError("Name must be a non-empty string.")
        return v.strip()


# In-repo agent wrappers depend on the SDK sources; agent builds get them as the `sdk` context.
SDK_PYTHON_PATH = Path("sdk/python")


def get_agent_path(name: str) -> Path:
    agents_dir = Path("agents")
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
                "--build-context",
                f"sdk={SDK_PYTHON_PATH.resolve()}",
                "-t",
                docker_image_name,
                "--load",
                ".",
            ],
            cwd=self.agent_path,
            check=True,
        )
        return docker_image_name
