import asyncio
import os
import sys
from asyncio.streams import StreamReader
from pathlib import Path

import toml
from sse import project
from sse.prompt import task_prompt

from config import CONFIG_TEMPLATE


def generate_config(api_key: str, base_url: str, model: str, mcp_url: str):
    global CONFIG_TEMPLATE
    CONFIG_TEMPLATE["model"] = model
    CONFIG_TEMPLATE["review_model"] = model
    CONFIG_TEMPLATE["model_providers"]["ssebench"]["base_url"] = base_url
    CONFIG_TEMPLATE["mcp_servers"]["ssebench"]["url"] = mcp_url

    home = os.getenv("HOME", "/root")
    codex_config_folder = Path(home) / ".codex"
    codex_config_folder.mkdir()
    with open(codex_config_folder / "config.toml", "w") as f:
        toml.dump(CONFIG_TEMPLATE, f)


async def stream_output(stream: StreamReader, prefix: str = ""):
    """
    Reads from a stream line-by-line and prints it with a prefix.
    This runs as a separate, concurrent task.
    """

    buf = b""

    while True:
        try:
            chunk = await stream.read(4096)
            buf += chunk
            line_sep = b"\n"
            while line_sep in buf:
                first_line, buf = buf.split(line_sep, maxsplit=1)
                print(f"{prefix} {first_line.decode().strip()}", flush=True)
            if len(chunk) == 0:
                # EOF, prints whatever we have in buf
                print(f"{prefix} {buf.decode().strip()}", flush=True)
                break

        except Exception as e:
            print(f"Error reading stream {prefix}: {e}", file=sys.stderr)
            continue


async def run_codex():
    command_args = [
        "codex",
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--json",
    ]

    process = await asyncio.create_subprocess_exec(
        *command_args,
        cwd=project.source,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE,
    )

    if process.stdin:
        process.stdin.write(task_prompt().encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()

    assert process.stdout is not None
    assert process.stderr is not None

    stdout_task = asyncio.create_task(stream_output(process.stdout, prefix="[STDOUT]"))
    stderr_task = asyncio.create_task(stream_output(process.stderr, prefix="[STDERR]"))

    _ = await process.wait()
    _ = await asyncio.gather(stdout_task, stderr_task)
    print("[codex] exited")


async def main():
    """
    Main function that configures and launches the Codex agent.
    Assumes MCP server is already running on http://localhost:3000/mcp
    """
    try:
        model_name = os.environ["SSE_MODEL_NAME"]
        base_url = os.environ["SSE_BASE_URL"]
        api_key = os.environ["SSE_API_KEY"]
    except KeyError as _:
        return

    generate_config(api_key, base_url, model_name, "http://localhost:3000/mcp")

    # Launch Codex agent
    process_task = asyncio.create_task(run_codex())
    await process_task


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("killed")
