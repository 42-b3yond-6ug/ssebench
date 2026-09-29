import logging

from sse import project
from sse.ai import OpenCodeAgent, build_opencode_config

logger = logging.getLogger(__name__)


def build_plugin_opencode_config():
    """
    Build an opencode config for the plugin to use AI.
    The model is the run's LiteLLM model, taken from the `SSE_*` environment
    variables. Raises ValueError if they are not set.
    """
    logger.info("Using SSEBench built-in Model.")
    return build_opencode_config()


_src_path = project.source.absolute()
opencode_agent = OpenCodeAgent(str(_src_path), config=build_plugin_opencode_config())
