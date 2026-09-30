"""Configuration for SSEBench MCP Server."""

import os
from dataclasses import dataclass
from enum import IntEnum


class DifficultyLevel(IntEnum):
    """Difficulty levels that control which tests are run during test_patch."""

    FULL_ASSISTANCE = 0  # Build + Func + Security (PoC) tests + Intent tests
    NO_INTENT_TEST = 1  # Build + Func tests + Security (PoC) tests
    NO_FUTURE_TEST = 2  # Build + Func tests only
    BUILD_ONLY = 3  # Build only
    NO_BUILD = 4  # Nothing (for debugging)


# Backward compatibility alias
Difficulty = DifficultyLevel


@dataclass(frozen=True)
class TestConfig:
    """Configuration for test execution in test_patch tool."""

    difficulty: DifficultyLevel
    enable_build: bool
    enable_function_test: bool
    enable_security_test: bool
    enable_intent_test: bool

    @classmethod
    def from_difficulty(cls, difficulty: DifficultyLevel) -> "TestConfig":
        """Create a TestConfig from a difficulty level."""
        return cls(
            difficulty=difficulty,
            enable_build=difficulty <= DifficultyLevel.BUILD_ONLY,
            enable_function_test=difficulty <= DifficultyLevel.NO_FUTURE_TEST,
            enable_security_test=difficulty <= DifficultyLevel.NO_INTENT_TEST,
            enable_intent_test=difficulty <= DifficultyLevel.FULL_ASSISTANCE,
        )


# Backward compatibility alias
TestToolConfig = TestConfig


@dataclass
class McpConfig:
    test_config: TestConfig

    # Backward compatibility property
    @property
    def test_tool_config(self) -> TestConfig:
        return self.test_config


def load_mcp_config() -> McpConfig:
    """Load configuration from environment variables.

    Returns:
        McpConfig object with test configuration.
    """
    env_key = "SSE_DIFFICULTY"
    raw_val = os.getenv(env_key)

    if raw_val is None:
        print(f"[{env_key}] not set. Defaulting to NO_FUTURE_TEST.")
        return McpConfig(TestConfig.from_difficulty(DifficultyLevel.NO_FUTURE_TEST))

    try:
        level = DifficultyLevel(int(raw_val))
    except ValueError:
        raise ValueError(f"{env_key} must be an integer from 0 to 4, got {raw_val!r}") from None

    print(f"[{env_key}] Found: {raw_val} -> {level.name}")
    return McpConfig(TestConfig.from_difficulty(level))
