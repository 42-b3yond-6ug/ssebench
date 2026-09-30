import asyncio
import logging

from fastmcp import Context, FastMCP
from fastmcp.utilities.logging import get_logger

from config import McpConfig, load_mcp_config
from evaluator import test_patch_internal

INTERNAL_ERROR_PROMPT = "An internal testing failure occurred. Your patch is not responsible for this failure."


def build_mcp(config: McpConfig):
    to_client_logger = get_logger(name="fastmcp.server.context.to_client")
    to_client_logger.setLevel(level=logging.DEBUG)
    mcp = FastMCP("ssebench MCP Server")

    @mcp.tool
    async def test_patch(ctx: Context) -> str:  # pyright: ignore[reportUnusedFunction]
        try:
            result = await test_patch_internal(config.test_tool_config)
            await ctx.debug(f"[mcp] Checks that ran passed={result.ok()}")
            return str(result)
        except Exception:
            return INTERNAL_ERROR_PROMPT

    return mcp


async def main():
    config = load_mcp_config()

    server = build_mcp(config)
    try:
        await server.run_http_async(port=3000, show_banner=False)
    except asyncio.CancelledError:
        print("[mcp] Server shutting down.")


if __name__ == "__main__":
    asyncio.run(main())
