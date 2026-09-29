import asyncio
import os
import sys
from asyncio.streams import StreamReader
from pathlib import Path

import toml
from sse import project

from config import CONFIG_TEMPLATE

metadata = project.metadata
task_description = metadata.task_description

if task_description.crash_report:
    with open(Path("/ssebench") / task_description.crash_report[0]) as f:
        vuln = f.read()
elif task_description.bug_description:
    vuln = task_description.bug_description
elif task_description.issue:
    vuln = task_description.issue
else:
    raise RuntimeError("No available vulnerability description!")


def generate_config(api_key: str, base_url: str, model: str, mcp_url: str):
    global CONFIG_TEMPLATE
    CONFIG_TEMPLATE["model"] = model
    CONFIG_TEMPLATE["review_model"] = model
    CONFIG_TEMPLATE["model_providers"]["ssebench"]["base_url"] = base_url
    CONFIG_TEMPLATE["mcp_servers"]["ssebench"]["url"] = mcp_url

    codex_config_folder = Path.home() / ".codex"
    codex_config_folder.mkdir(parents=True, exist_ok=True)
    with open(codex_config_folder / "config.toml", "w") as f:
        toml.dump(CONFIG_TEMPLATE, f)


USER_PROMPT = f"""
  You are an AI agent performing a critical computer security task.
  We are working with other AI agents to help each other in our task to discover vulnerabilities,
  generate proof-of-vulnerabilities, and patch the vulnerable code.

  Project is named {project.metadata.project}

  All relevant code to the project is written in {project.metadata.language}.

  <instructions>
  
  A vulnerability has been identified in the source code. You are responsible
  for patching this vulnerability by editing the source code. The vulnerability
  must be fixed WITHOUT changing the intended behavior of the relevant code. Think
  step-by-step about how to use the tools available to you in order to produce
  a safe and functional patch. Your patch will be tested for functionality by
  running the project's test suite and for safety by running our existing proof-of-vulnerability.

  Do not attempt patches which filter potentially malicious payloads with deny
  or allow lists of strings. Instead, focus on addressing the root cause of the
  issue.

  <important>You must try to fully fix the vulnerability. We can only test it
  against known proof-of-vulnerability inputs, but your fix should be able stop
  all inputs from triggering the vulnerability or crashing the program. Be sure
  you understand the vulnerability well enough to fix it in its entirety!</important>

  <rule>You may only modify {"Java" if project.metadata.language == "java" else "C/C++"} source files
  in this directory: {project.source}</rule>

  <rule>You may not modify a fuzzing harness</rule>

  You should begin by making sure you fully understand the vulnerability. Then
  think of a few different strategies that could be used to patch the vulnerability.
  Finally, pick the strategy that seems best and begin.

  After generating a patch, use the `test_patch` tool to evaluate it. The tool will evaluate if:
  - The project can be compiled.
  - The project can process all the proof-of-vulnerability inputs without crashing.
  - The project can pass all the functionality tests.
  
  Continue improving your patch and do not stop until all `test_patch` checks pass.

  Do not attempt to build the project yourself. Never run make, cmake, or any manual build commands. Only the `test_patch` tool is allowed to perform builds.

  If the `test_patch` tool reports an internal error, you may stop. Internal errors are not caused by your patch.

  </instructions>

  {vuln}

"""


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
        process.stdin.write(USER_PROMPT.encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()

    assert process.stdout is not None
    assert process.stderr is not None

    stdout_task = asyncio.create_task(stream_output(process.stdout, prefix="[STDOUT]"))
    stderr_task = asyncio.create_task(stream_output(process.stderr, prefix="[STDERR]"))

    return_code = await process.wait()
    _ = await asyncio.gather(stdout_task, stderr_task)
    print(f"[codex] exited with code {return_code}")
    return return_code


async def main():
    """
    Main function that configures and launches the Codex agent.
    Assumes MCP server is already running on http://localhost:3000/mcp
    """
    try:
        model_name = os.environ["SSE_MODEL_NAME"]
        base_url = os.environ["SSE_BASE_URL"]
        api_key = os.environ["SSE_API_KEY"]
    except KeyError as e:
        print(f"[codex] missing environment variable {e}", file=sys.stderr)
        return 1

    generate_config(api_key, base_url, model_name, "http://localhost:3000/mcp")

    return await run_codex()


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("killed")
