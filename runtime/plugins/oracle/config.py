"""OpenCode agent factory for the oracle plugin.

The agent uses the run's model through LiteLLM, taken from the SSE_* environment
variables. build_opencode_config raises ValueError if they are not set, so call
this only after checking them.
"""

from __future__ import annotations

import logging

from sse import project
from sse.ai import OpenCodeAgent, build_opencode_config

logger = logging.getLogger(__name__)


def make_opencode_agent() -> OpenCodeAgent:
    """An OpenCode agent rooted at the project source, using the run's model."""
    logger.info("Using the run's built-in model through LiteLLM")
    source = str(project.source.absolute())
    return OpenCodeAgent(source, config=build_opencode_config())
