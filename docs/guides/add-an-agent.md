---
outline: deep
---

# Add an agent

An agent is the program that SSEBench runs inside the task container to fix the
vulnerability: a wrapper around a coding assistant's command line, a scripted
pipeline, or your own model loop. Anything that can read the task, edit the
source tree and exit can be one. This guide builds a small agent, then lists
what every agent can rely on and what it must not do.

Read [Architecture](/concepts/architecture) first if you have not seen how a
run is put together, and [Extension points](/guides/extension-points#container-contract)
for the container contract this guide refers to.

## Overview

An agent is a folder in `agents/`. Its name is the value of `ssebench run --agent`:

```
agents/example-shell/
├── agent.yaml            names the agent's image
├── Dockerfile            builds on the tool layer; its CMD is the agent command
├── .dockerignore
└── example-shell-sse/    the wrapper, a Python package that uses the `sse` SDK
    ├── pyproject.toml
    └── main.py
```

Only `agent.yaml` and the `Dockerfile` are required. The wrapper is the
convention of the bundled agents:

| Agent | What it runs | Wrapper |
|---|---|---|
| `claude-code` | Claude Code, pointed at the LiteLLM proxy | `claude-code-sse`: starts it and converts its output to `dialog.jsonl` |
| `codex` | OpenAI Codex CLI | `codex-sse` |
| `opencode` | The OpenCode server that the entrypoint starts | `opencode-sse`: an HTTP client of that server |
| `dummy` | `echo`; it changes nothing | none |
| `reference` | Applies the task's known fix | `reference-sse`, the smallest wrapper that uses the SDK |

`ssebench run` builds your image on top of the task's tool image and starts a
container. The container's entrypoint starts the daemon and the MCP server,
runs your command as the unprivileged user `model`, and, when your command
exits or the time limit is reached, grades the source tree it leaves behind.
See [What happens during a run](/concepts/architecture#what-happens-during-a-run).

## Build a minimal agent

`example-shell` builds the project through the daemon, calls the `test_patch`
tool, applies no fix, and writes a session for the web UI. It makes no model
call, so it needs no provider key, like the `dummy` agent, but it uses every
interface a real agent uses. Create these files in a clone of SSEBench.

### 1. `agent.yaml`

```yaml
name: example-shell
```

### 2. The wrapper

`agents/example-shell/example-shell-sse/pyproject.toml`:

```toml
[project]
name = "example-shell-sse"
version = "1.0.0.dev0"
description = "Builds the project through the daemon and applies no fix"
requires-python = ">=3.12"
dependencies = [
  "fastmcp",
  "ssebench-sdk",
]

[tool.uv.sources]
ssebench-sdk = { workspace = true }
```

Every `agents/*/*-sse` folder is a member of the repository's
[uv workspace](/contributing/project-structure#python-workspace), so the
wrapper installs the SDK from the workspace and its version is the one in
`VERSION`, in Python's spelling (`1.0.0-dev` is `1.0.0.dev0`). Then `uv run
tools/release/bump.py --check` passes, and `just release <version>` keeps the
version in step later.

`agents/example-shell/example-shell-sse/main.py`:

```python
"""Example agent: check the unpatched project through the daemon and the MCP server, fix nothing.

It shows the parts every agent has: read the task with the `sse` SDK, run the
build and `test_patch`, and write `dialog.jsonl` for the web UI.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastmcp import Client
from sse import project
from sse.prompt import task_prompt

MCP_URL = "http://localhost:3000/mcp"
MAX_OUTPUT = 4000


class Dialog:
    """Appends entries in the dialog protocol to $SSE_ARCHIVE/dialog.jsonl."""

    def __init__(self) -> None:
        archive = Path(os.environ.get("SSE_ARCHIVE", "/tmp/sse-archive"))
        archive.mkdir(parents=True, exist_ok=True)
        self.file = (archive / "dialog.jsonl").open("w")
        self.seq = 0
        self.start = time.monotonic()

    def write(self, entry_type: str, **fields: Any) -> None:
        entry = {
            "seq": self.seq,
            "ts": datetime.now(UTC).isoformat(),
            "type": entry_type,
            **fields,
        }
        self.seq += 1
        self.file.write(json.dumps(entry) + "\n")
        self.file.flush()

    def tool(self, tool_id: str, name: str, ok: bool, output: str) -> None:
        output = output[:MAX_OUTPUT]
        result = {"result": output} if ok else {"error": output}
        self.write(
            "tool",
            tool_id=tool_id,
            name=name,
            status="success" if ok else "error",
            **result,
        )

    def complete(self, status: str, turns: int, message: str) -> None:
        self.write(
            "complete",
            status=status,
            turns=turns,
            duration_ms=int((time.monotonic() - self.start) * 1000),
            total_tokens={"in": 0, "out": 0},
            message=message,
        )
        self.file.close()


async def main() -> int:
    dialog = Dialog()
    dialog.write(
        "init",
        data={
            "task": project.metadata.id,
            "cwd": str(project.source),
            "model": os.environ.get("SSE_MODEL_NAME", "none"),
            "agent": "example-shell",
        },
    )
    dialog.write("prompt", content=task_prompt())

    # The SDK asks the daemon to build a copy of the source tree, which works in
    # sandbox and sidecar mode alike.
    dialog.write("tool", tool_id="build", name="build", status="running")
    build = project.build()
    dialog.tool("build", "build", build.is_success(), build.stdout + build.stderr)

    # test_patch is the tool a model-driven agent would call through MCP.
    dialog.write("tool", tool_id="test_patch", name="test_patch", status="running")
    async with Client(MCP_URL) as client:
        checked = await client.call_tool("test_patch", {})
    report = str(checked.data)
    dialog.tool("test_patch", "test_patch", report.startswith("Test succeeded"), report)

    dialog.write(
        "message",
        role="assistant",
        content=f"The build exited with {build.code}. I applied no fix.",
    )
    dialog.complete(
        "success", turns=1, message="Checked the project and changed nothing"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

### 3. The Dockerfile

`agents/example-shell/Dockerfile`:

```dockerfile
FROM ghcr.io/astral-sh/uv:0.12.20@sha256:100047e74f30778ab704942321a09750d6158739573ff58bf3924085cc6cd2d8 AS uv

FROM ssebench-agent

# The wrapper is a member of the uv workspace at the repository root, so /app
# holds the workspace files it needs (from the `workspace` build context) in the
# repository layout.
WORKDIR /app
COPY --from=workspace pyproject.toml uv.lock /app/
COPY --from=workspace sdk/python/pyproject.toml sdk/python/README.md /app/sdk/python/
COPY --from=workspace sdk/python/sse/ /app/sdk/python/sse/
COPY example-shell-sse/pyproject.toml /app/agents/example-shell/example-shell-sse/

# The run container cannot reach a package index, so the environment is built
# here, on a Python that the model user can execute (uv's default location is
# under /root).
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python UV_NO_CACHE=1 \
    uv sync --package example-shell-sse --frozen --no-dev --no-editable

COPY example-shell-sse/ /app/agents/example-shell/example-shell-sse/
WORKDIR /app/agents/example-shell/example-shell-sse

CMD ["/app/.venv/bin/python", "main.py"]
```

This is the Dockerfile of the `reference` agent with the names changed. Copy
`agents/reference/.dockerignore` next to it as well.

### 4. Lock the new package

The build installs from the lockfile with `--frozen`, so record the new
workspace member in `uv.lock` once, and commit the result with the agent:

```sh
uv lock
```

### 5. Run it

```sh
uv run ssebench run --local datasets/pilot --task gjson-196-bf4efcb \
  --agent example-shell --model claude-sonnet-4-6
```

`--model` is required for every agent but `reference`. It only has to name a
model in `models/`; this agent never calls it. The first run builds the case,
tool and agent images, and Docker's cache makes later runs quick; see the
[Quickstart](/getting-started/quickstart) and
[Image layers](/concepts/image-layers).

The container's log ends with the entrypoint's view of your agent:

```text
level=INFO service=ssebench msg="Agent command" cmd="/app/.venv/bin/python main.py"
level=INFO service=ssebench msg="Agent started" pid=176
level=INFO service=ssebench msg="Agent finished" status=0
```

### 6. Read the results

The run writes `results/gjson-196-bf4efcb/claude-sonnet-4-6/example-shell/`;
see [Results format](/concepts/results). Three files matter for an agent:

- `agent.log` holds the agent's standard output and error. This agent prints
  nothing, so it is empty.
- `dialog.jsonl` is what the web UI shows:

  ```text
  {"seq": 0, "type": "init", "data": {"task": "gjson-196-bf4efcb", "cwd": "/src/gjson", "model": "claude-sonnet-4-6", "agent": "example-shell"}, ...}
  {"seq": 2, "type": "tool", "tool_id": "build", "name": "build", "status": "running", ...}
  {"seq": 3, "type": "tool", "tool_id": "build", "name": "build", "status": "success", "result": "", ...}
  {"seq": 5, "type": "tool", "tool_id": "test_patch", "name": "test_patch", "status": "success", "result": "Test succeeded: All checks passed. Your patch is valid. You may stop now.", ...}
  {"seq": 7, "type": "complete", "status": "success", "turns": 1, "duration_ms": 14080, ...}
  ```

- `result.json` is the grade, `status: failed`: the build and the project's
  tests pass, and the proof of concept still triggers the bug, because the
  agent changed nothing.

  ```sh
  jq -c '.patch_result | del(.error_log)' results/gjson-196-bf4efcb/claude-sonnet-4-6/example-shell/result.json
  ```

  ```json
  {"status":"failed","build_success":true,"pov_passed":0,"pov_total":1,"func_test_success":true,"intent_test_success":false,"error_msg":"PoC failed: /ssebench/pocs/poc.go"}
  ```

::: warning `test_patch` is not the grade
`test_patch` reported success for an unpatched, vulnerable project. At the
default [difficulty level](/concepts/difficulty-levels), 2, it runs the build
and the project's tests, and withholds the proofs of concept and the hidden
tests. An agent that stops as soon as `test_patch` succeeds can still fail
grading. See [Grading and `test_patch`](/concepts/grading#grading-and-test-patch).
:::

The same agent folder also runs in sidecar mode, with `--mode sidecar` added to
the command; that mode is experimental (see
[Sandbox and sidecar](/concepts/sandbox-and-sidecar)).

Delete `agents/example-shell/` when you are done and restore `uv.lock` with
`git checkout uv.lock`. The rest of this guide describes each part.

## `agent.yaml`

```yaml
name: example-shell
```

| Key | Required | Meaning |
|---|---|---|
| `name` | yes | The agent's name in image names: `agent-<name>/<task-id>:<version>`, in lowercase. |
| `version` | | The image tag. Defaults to the SSEBench version; you rarely need it. |

Unknown keys are rejected. [Configuration files](/reference/configuration#agent-yaml)
is the reference. Keep `name` equal to the folder name: `--agent` takes the
folder name, and the results directory, the container's `ssebench.agent` label
and `config.agent` in the results all use it, while the images use `name`.

## The Dockerfile contract

### How it is built

`ssebench run` builds each agent with `docker buildx build`, in the agent's
folder as the build context, and passes two named build contexts:

| Context | Is | Use it to |
|---|---|---|
| `ssebench-agent` | The tool image of the run | Start with `FROM ssebench-agent`. It is not an image name; the CLI resolves it. |
| `workspace` | The SSEBench home, the repository root | Copy the SDK and the lockfile in with `COPY --from=workspace`. |

The tool image is the case image plus the SSEBench runtime. So, in sandbox
mode, an agent starts from:

- Ubuntu 24.04 with `git`, `curl`, `wget`, `patch` and `uv`, and the task's
  language toolchain (Go, or Clang and the C tooling, or Rust);
- the project's source tree at the `source` path of the task, owned by `model`,
  with its history replaced by a single commit;
- the user `model` (uid 1000), and the runtime: the entrypoint, the daemon, the
  MCP server and the evaluator.

Do not rely on the base for your Python: the Go image has none, and the C and
Rust images have a system Python without your packages. There is no `sudo`, and
no package index to reach when the agent runs. In sidecar mode the tool image is
task-independent and has no project toolchain at all, and one agent image
serves every task; see [Image layers](/concepts/image-layers#agent).

The build itself has the network, like any `docker build`. The run does not.

### How the agent is started

The entrypoint is the image's `ENTRYPOINT`. Your image's `CMD` reaches it as
arguments, and it runs them as `model`. What the agent gets:

| | |
|---|---|
| Command | The `CMD` words joined by spaces and run with `su -p -s /bin/bash model -c`. Words that need quoting lose it: `["bash", "-c", "echo 'a b'"]` prints an empty line. Use a script, or a program with simple arguments: `["./run.sh"]`, `["/app/.venv/bin/python", "main.py"]`. |
| User | `model`, uid 1000, with no root and no `sudo`. It can write to its home, `/tmp`, the source tree and `$SSE_ARCHIVE`. `/app`, `/opt` and `/usr/local` belong to root: `chown` what the agent must write when you build the image. |
| Working directory | The last `WORKDIR` of the image, which is the case image's (the project's directory, `/src/gjson` for `gjson-196-bf4efcb`) unless your Dockerfile sets one. Set your own, and find the source through `sse.project.source`. |
| `HOME` | `/root`, which `model` cannot read: `su -p` keeps root's environment, and `git` and `uv` fail on it. Set `HOME` first, to the home that the user database gives `model` (`pwd.getpwuid(os.getuid()).pw_dir` in Python, `getent passwd model` in a shell). It holds the git identity, `SSEBench <bench@ssebench.local>`. Do not assume `/home/model`: in the Ubuntu-based images `model` is the renamed `ubuntu` user, with the home `/home/ubuntu`, and `/home/model` is an empty directory where `git commit` fails with `Author identity unknown`. |
| Input and output | Standard input is `/dev/null`. Standard output and error go to `agent.log` in the results directory. |
| Session | Its own session and process group. |
| Ready | The daemon's socket and the MCP server answer before the agent starts. In sandbox mode the entrypoint also starts the OpenCode server, on port 4096, without waiting for it. |
| Plugins | When the run selects [plugins](/concepts/plugins-and-hooks) with `--plugin`, those at `before-agent` finish before the agent starts, and those at `after-agent` run once it has exited. |
| Environment | The variables below, and the `ENV` of the image. |

The environment, from `ssebench run` and the entrypoint; see
[Environment variables](/reference/environment#inside-the-task-container)
for the complete list:

| Variable | Value |
|---|---|
| `SSE_BASE_URL` | The LiteLLM proxy, `http://litellm:4000` |
| `SSE_API_KEY` | The run's LiteLLM key |
| `SSE_MODEL_NAME` | The selected model, as named in `models/*.yaml` |
| `SSE_DIFFICULTY` | The [difficulty level](/concepts/difficulty-levels), 0 to 4 |
| `TIMEOUT` | The agent's time limit in seconds (`--timeout`, 3600 by default) |
| `SSE_ARCHIVE` | The results directory, `/tmp/sse-archive` |
| `SSE_DAEMON_SOCKET` | The daemon's socket, `/tmp/sse.sock`; the SDK reads it |

In a reference run `SSE_MODEL_NAME` is `none`, and `SSE_API_KEY` and
`SSE_BASE_URL` are empty.

### How it ends

- **Exit.** The agent decides when it is done and exits. The container takes
  its exit status, and a non-zero status is logged, but grading does not depend
  on it: the evaluator runs whatever the agent did.
- **Time limit.** At `TIMEOUT` seconds the entrypoint kills the agent's process
  group with `SIGKILL`, and the exit status is 124. The agent gets no chance to
  clean up, so an agent that wants to end its dialog with `complete` must stop
  before the limit. The result records `agent_timeout: true`.
- **What is graded.** The daemon diffs the source tree against its initial
  commit when the agent phase ends, whether or not the agent committed. Files
  the agent leaves behind that `.gitignore` does not ignore become part of the
  patch, so delete scratch files; see
  [Capturing the patch](/concepts/grading#_1-capturing-the-patch). The bundled
  agents' prompt asks the model for a commit.

### Dependencies must be in the image

The run container cannot reach the internet: by default it is on an internal
network where it reaches the LiteLLM proxy and nothing else, and names such as
`pypi.org` or `github.com` do not resolve; see
[Integrity and egress](/deployment/integrity-and-egress). So everything the
agent needs must be installed when the image is built: its Python packages,
its Python, its Node.js, its model CLI.

The `Dockerfile` above shows the pattern for Python:

- install into an environment that already exists when the container starts
  (`uv sync --frozen` in a `RUN` step, then run `/app/.venv/bin/python`);
- put uv's Python where `model` can execute it, with `UV_PYTHON_INSTALL_DIR`
  set to a directory outside `/root`;
- do not fetch anything from the command: `npm install` and a `uv run` that
  has to sync the environment would need the network. The bundled wrappers
  install their environments in their images, and their `run.sh` scripts start
  with `uv run --offline --no-sync main.py`.

Do not pass `--egress open` to make an agent work: it gives the agent the
upstream repository and its fix, and such results are not comparable with
restricted ones.

### What an agent must not do

The [integrity model](/concepts/integrity) keeps the answer away from the
agent, and a run is only meaningful if the agent works honestly:

- Do not look for the reference patch, the hidden tests or the proofs of
  concept. `/ssebench`, `/ssebench-repo` and the daemon's admin socket are
  readable by root only, and the history of the project is one commit. Do not
  call `sse.reference.get_reference_patch()`: it is for tooling that runs after
  the agent.
- Do not reach the internet, and do not depend on it. Requests to the LiteLLM
  proxy are the exception. A provider-hosted tool that a request switches on,
  such as web search, runs outside the network policy, which cannot see it;
  leave such tools off.
- Do not run as, or expect to become, root.
- Do not put a provider key in the image. The run's own key arrives in
  `SSE_API_KEY`, and it can use only the selected model.
- Do not treat `dialog.jsonl` as evidence of what the agent did: the agent
  writes it.

If you find a way to reach the answer from inside the container, report it
privately, as described in [Reporting a bypass](/concepts/integrity#reporting-a-bypass).

## Talk to the model

Agents never call a provider directly. The proxy at `SSE_BASE_URL` speaks the
OpenAI API (`/v1/chat/completions`, `/v1/responses`) and the Anthropic API
(`/v1/messages`), and translates it for the model's provider, so any agent runs
with any model in `models/`. Authenticate with `SSE_API_KEY`, and name the model
`SSE_MODEL_NAME`:

```python
import os

import httpx

reply = httpx.post(
    f"{os.environ['SSE_BASE_URL']}/v1/chat/completions",
    headers={"Authorization": f"Bearer {os.environ['SSE_API_KEY']}"},
    json={
        "model": os.environ["SSE_MODEL_NAME"],
        "messages": [{"role": "user", "content": "Say hello in five words."}],
    },
    timeout=600,
)
reply.raise_for_status()
body = reply.json()
text, usage = body["choices"][0]["message"]["content"], body["usage"]
```

`httpx` is a dependency of the SDK. The run's key can use only the selected
model, `GET $SSE_BASE_URL/models` lists just that one, and each run has a budget
of 10 US dollars. The CLI records what the run spent as `spend` in the
[summary](/concepts/results#the-summary). An agent that wraps another CLI points
it at the proxy the way the bundled agents do; the table in
[LiteLLM proxy](/concepts/litellm-proxy#what-the-agent-gets) lists their settings.

## Check the work

### The `test_patch` tool

The MCP server gives the agent one tool, `test_patch`, that runs the checks the
difficulty level allows on the current source tree, uncommitted changes
included. It is a Streamable HTTP server at `http://localhost:3000/mcp`. Any MCP
client can call it; `example-shell` uses FastMCP's:

```python
from fastmcp import Client

async with Client("http://localhost:3000/mcp") as client:
    checked = await client.call_tool("test_patch", {})
print(checked.data)   # "Test succeeded: ..." or "Test failed: <reason> ..."
```

A call runs a full build and test cycle, so give the tool call a generous
timeout. An agent that drives a model registers the server as a tool of the
model; the bundled agents register it under the name `ssebench`.
[MCP server](/reference/mcp-server) describes the results and the difficulty
levels.

### The SDK

The `sse` package is the other way in. It talks to the daemon, and unlike the
MCP tool it gives each check separately and structured:

| Call | Does |
|---|---|
| `sse.project.metadata`, `project.source` | The task: its id, project, language, source path, report texts and scripts. Fetched when the module is imported. |
| `project.build()`, `run_poc(poc)`, `function_test()`, `intent_test()` | One check each, on a copy of the source tree. They return a `ScriptResult` (`code`, `stdout`, `stderr`, `is_success()`); a failing check is a result, not an error. |
| `sse.tools.bash.execute(command)` | A persistent shell in the source tree, as `model`. |
| `sse.prompt.task_prompt()` | The prompt the bundled agents give their model: the same text for every agent; see [Task prompt](/concepts/prompt). |

A check that the difficulty level withholds raises `SDKError`. `sse.project`
and `sse.prompt` ask the daemon for the task when they are imported, so they
work only inside a task container. See the [Python SDK](/reference/python-sdk)
reference.

In sidecar mode the agent's container has no project toolchain, so builds and
tests have to go through the SDK or `test_patch`: they run in the task
container. An agent that uses them works in both modes.

## Report the session

The web UI shows what an agent did from `dialog.jsonl`, in the
[dialog protocol](/reference/dialog-protocol): one JSON object per line, in the
file `$SSE_ARCHIVE/dialog.jsonl`. The daemon serves it at
`GET /agent/dialog?since=<seq>`, and the web UI polls that while the run is
live, so flush after every entry. Nothing else reads it: grading ignores it, and
an agent without one, like `dummy`, just shows an empty dialog.

A dialog is these entries, in this order:

```text
init  ->  prompt  ->  ( message | thinking | tool )*  ->  complete
```

- every entry has `seq`, counting up from 0, `ts` (an ISO 8601 timestamp) and
  `type`;
- a tool call is two `tool` entries with the same `tool_id`: one with
  `status: "running"` and one with `"success"` or `"error"`;
- `message` entries may carry `tokens: {"in": …, "out": …}`;
- open the file for writing, not appending, and write `complete` last.

Lines that are not JSON, or have no `seq`, are skipped. The `Dialog` class in
`example-shell` is all it takes; `agents/reference/reference-sse/main.py` has the
same in a shorter form, and `agents/claude-code/claude-code-sse/main.py` is the
canonical implementation, which converts Claude Code's `stream-json` output.

To see what the web UI will get, keep the container and ask its daemon:

```sh
uv run ssebench run --local datasets/pilot --task gjson-196-bf4efcb \
  --agent example-shell --model claude-sonnet-4-6 --keep-container

# in another terminal
id=$(docker ps --filter label=ssebench.agent=example-shell --format '{{.ID}}')
ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$id")
curl "http://$ip:4263/agent/dialog?since=5"
docker stop "$id"
```

Stopping a kept container makes `ssebench run` log a non-zero exit; the results
are written all the same. Or open the [web UI](/webui/), which lists kept
containers.

## Test and debug

- **Logs.** `agent.log`, `daemon.log`, `mcp.log` and `evaluator.log` in the
  results directory hold what each process printed. The CLI shows the entrypoint,
  daemon and evaluator output while it runs, but not `agent.log`.
- **A shell in the container.** Run with `--keep-container`, then
  `docker exec -it -u model <container> bash`.
- **Restricted egress.** Run your agent with the default `--egress`. If it works
  only with `--egress open`, it installs something at run time.
  `tests/agents/` runs each bundled agent on an internal Docker network with no
  internet and a stub model, as `uv run pytest tests/agents -m agents`; add a
  case to `CASES` in `tests/agents/test_offline.py` for a new agent.
- **Difficulty.** `--difficulty 0` lets the agent's checks run everything, `4`
  nothing; try the levels your agent should handle.
- **Static checks.** `just lint python` runs ruff, at 88 columns for `agents/`,
  and basedpyright on the wrapper. `uv run tools/release/bump.py --check`
  checks the version of the wrapper against `VERSION`.
- **Pickers.** `just pick` lists the folders of `agents/` that have an
  `agent.yaml`, and the web UI lists every folder of `agents/`, so keep helper
  files out of `agents/` itself.

### Common errors

| Symptom | Cause and fix |
|---|---|
| `FileNotFoundError: Agent <name> does not exist.` | No folder `agents/<name>`. The CLI prints a Python traceback for this. |
| `ValidationError ... Extra inputs are not permitted` | `agent.yaml` has a key that is not `name` or `version`. |
| `The lockfile at uv.lock needs to be updated, but --frozen was provided: Missing workspace member` | A new wrapper package is not in `uv.lock`. Run `uv lock`. |
| `warning: unable to access '/root/.gitconfig': Permission denied`, or `uv` cannot create `/root/.cache/uv` | `HOME` is still `/root`. Set it to the home of `model`. |
| `Author identity unknown` | `HOME` points at a directory without a git identity. Use the home from the user database, or `git -c user.name=… -c user.email=… commit`. |
| `Could not resolve host`, `Failed to download`, `dns error` | The agent reaches for the network at run time. Install it in the image. |
| The agent's arguments arrive without their quotes | The entrypoint joins `CMD` with spaces. Put the command in a script. |
| `agent.log` is empty | The agent printed nothing, or exited before it did. Print to standard error and check the exit status in the entrypoint's log. |

## Next steps

- [Dialog protocol](/reference/dialog-protocol): every entry type
- [MCP server](/reference/mcp-server): `test_patch`
- [Python SDK](/reference/python-sdk): the `sse` package
- [Add a model](/guides/add-a-model): give the agent another model to run with
- [Write a plugin](/guides/write-a-plugin): run a program around your agent
- [Integrity model](/concepts/integrity): what an agent can and cannot reach
