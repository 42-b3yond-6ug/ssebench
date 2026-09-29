---
outline: [2, 3]
---

# Python SDK

The Python SDK, `ssebench-sdk`, is imported as `sse`. Code that runs inside a
task container uses it: agents read the task and run the checks the
[difficulty level](/concepts/difficulty-levels) allows, the evaluator grades the
patch, and post-agent tooling reads the reference patch. It talks to the
[daemon](/reference/daemon-api) over the Unix socket in `SSE_DAEMON_SOCKET`,
which the entrypoint sets.

```python
from sse import project

print(project.metadata.id, project.source)
result = project.build()
if result.is_success():
    print(project.function_test().stdout)
```

`sse.project` and `sse.prompt` ask the daemon for the task when they are
imported, so they work only inside a task container. Errors from the daemon,
such as a check that the difficulty level withholds, raise
[`SDKError`](#sse-error); a check that runs and fails is a
[`ScriptResult`](#class-scriptresult) with a non-zero exit code.

## Install and versions

The SDK is on PyPI as `ssebench-sdk`. An agent that runs in a task container
installs it into its own environment:

```sh
pip install ssebench-sdk==<version>
```

It needs Python 3.12 or newer. The agents in this repository, the evaluator and
the MCP server are members of the repository's uv workspace and use the SDK
from the workspace (`ssebench-sdk = { workspace = true }`), so they always get
the version of the checkout.

The SDK and the daemon are released together with one version, and
`ssebench-sdk` `X` works with `ssebench-daemon` `X`; see
[Releasing and versioning](/contributing/releasing). Pin the SDK to the version
of the SSEBench release that built your task image. When the SDK connects to
the daemon, it reads the daemon's version from
[`GET /version`](/reference/daemon-api) and logs a warning if it differs from
`sse.__version__`:

```text
SDK version (1.1.0) does not match daemon version (1.2.0)
```

The warning does not stop the run, but nothing promises that a mismatched SDK
and daemon agree on the API, so treat it as a sign to fix the pin. Python
packages write a pre-release as `1.2.0rc1`, the daemon and `VERSION` as
`1.2.0-rc.1`; the SDK treats both as the same release.

<!-- The module sections are generated from the docstrings in sdk/python/sse/
by tools/docs/reference.py; edit the docstrings, then run `just docs-gen`. -->

<!-- generated: sdk modules -->

- [`sse`](#sse)
- [`sse.project`](#sse-project)
- [`sse.metadata`](#sse-metadata)
- [`sse.prompt`](#sse-prompt)
- [`sse.tools.bencher`](#sse-tools-bencher)
- [`sse.tools.bash`](#sse-tools-bash)
- [`sse.grading`](#sse-grading)
- [`sse.reference`](#sse-reference)
- [`sse.helper`](#sse-helper)
- [`sse.error`](#sse-error)
- [`sse.daemon`](#sse-daemon)
- [`sse.ai`](#sse-ai)

<!-- end generated -->

<!-- generated: sdk api -->

## `sse`

SSEBench SDK: the task, and the build, test and grading actions of the daemon, for code in a task container.

Agents, plugins and the evaluator run inside the task container and import this package as
`sse`. It talks to `ssebench-daemon` over the Unix socket in `SSE_DAEMON_SOCKET`; see
`sse.daemon`. `import sse` loads `sse.ai`, `sse.grading`, `sse.reference`
and `sse.tools` without contacting the daemon; `sse.project` and `sse.prompt` ask
the daemon for the task when they are imported.

## `sse.project`

The task of this container: its metadata, its capabilities and the checks an agent may run.

Importing this module asks the daemon for the task's metadata and capabilities, so it works only
where a daemon answers: inside a task container, or with `SSE_DAEMON_SOCKET` pointing at one.
The checks go to the daemon's agent-facing socket, which refuses those that the run's difficulty
level withholds: they raise `SDKError`. The types of the metadata are in
`sse.metadata`.

### `init_metadata()`

```python
def init_metadata() -> Metadata
```

Ask the daemon for the task's metadata. Importing the module does this once; use `metadata`.

### `init_capabilities()`

```python
def init_capabilities() -> Capabilities
```

Ask the daemon for the task's capabilities. Importing the module does this once; use `capabilities`.

### `metadata`

```python
metadata: Metadata
```

The task's metadata, fetched when the module is imported.

### `capabilities`

```python
capabilities: Capabilities
```

The task's capabilities, fetched when the module is imported.

### `source`

```python
source: Path
```

The project's source tree, which the agent edits (`metadata.source`).

### `all_poc`

```python
all_poc: list[Path]
```

The task's proof-of-concept inputs (`metadata.poc`).

### `build()`

```python
def build() -> ScriptResult
```

Build the project from a copy of its source tree, and keep the build for `run_poc`.

Raises `SDKError` when the task has no build script, when the difficulty
level withholds the build, or when the daemon fails. A failed build is a result with a
non-zero exit code, not an error.

### `run_poc()`

```python
def run_poc(poc: Path) -> ScriptResult
```

Run one proof of concept, one of `all_poc`, against the last `build`.

Exit code 0 means that the vulnerability no longer triggers. Without a build the result has
exit code -1. Raises `SDKError` as `build` does.

### `function_test()`

```python
def function_test() -> ScriptResult
```

Run the project's tests on a copy of its source tree.

Raises `SDKError` as `build` does.

### `intent_test()`

```python
def intent_test() -> ScriptResult
```

Apply the hidden tests of the fix to a copy of the source tree and run the project's tests.

Hidden tests that do not apply to the agent's changes give exit code 1. Raises
`SDKError` as `build` does.

## `sse.metadata`

Types of the task's public metadata, as the daemon's `GET /project` and `GET /capabilities`
return them.

They live apart from `sse.project`, which asks the daemon for them on import, so that code
built on them, such as `sse.prompt.build_prompt`, works without a daemon.

### `class TaskDescription`

```python
@dataclass
class TaskDescription(
    issue: str | None,
    crash_report: list[str] | None,
    bug_description: str | None,
)
```

What the agent is told about the vulnerability.

| Field | Type | Description |
|---|---|---|
| `issue` | `str \| None` | Issue text. |
| `crash_report` | `list[str] \| None` | Contents of the report files, such as the upstream issue or a sanitizer log, in the order of the task config. |
| `bug_description` | `str \| None` | Short description of the bug. |

### `class Metadata`

```python
@dataclass
class Metadata(
    id: str,
    project: str,
    language: str,
    source: Path,
    task_description: TaskDescription,
    poc: list[Path],
    build_script: str | None = None,
    test_script: str | None = None,
)
```

The task, as the daemon's `GET /project` returns it. Reference material is left out.

| Field | Type | Description |
|---|---|---|
| `id` | `str` | Task ID. |
| `project` | `str` | Name of the upstream project. |
| `language` | `str` | Language of the project: `c`, `go` or `rust`. |
| `source` | `Path` | The project's source tree, which the agent edits. |
| `task_description` | `TaskDescription` | What the agent is told about the vulnerability. |
| `poc` | `list[Path]` | Proof-of-concept inputs, to pass to `sse.project.run_poc`. Only the daemon can read them. |
| `build_script` | `str \| None` | Contents of the build script, if the task has one. |
| `test_script` | `str \| None` | Contents of the test script, if the task has one. |

### `class Capabilities`

```python
@dataclass
class Capabilities(
    can_build: bool,
    can_run_poc: bool,
    poc_count: int,
    has_function_test: bool,
    has_intent_test: bool,
)
```

The checks the task supports, as the daemon's `GET /capabilities` returns them.

The difficulty level can still withhold a supported check from the agent.

| Field | Type | Description |
|---|---|---|
| `can_build` | `bool` | The task has a build script. |
| `can_run_poc` | `bool` | The task has a run script and at least one proof of concept. |
| `poc_count` | `int` | Number of proofs of concept. |
| `has_function_test` | `bool` | The task has a test script. |
| `has_intent_test` | `bool` | The task has a test script and hidden tests of the fix. |

### `parse_metadata()`

```python
def parse_metadata(data: dict[str, Any]) -> Metadata
```

Build `Metadata` from the JSON object of the daemon's `GET /project`.

## `sse.prompt`

The task prompt that the bundled agents give their model.

`build_prompt` depends only on the task's public metadata, the daemon's
`GET /project`, so every agent that uses it sends the same text for a task.
That view holds the report contents and the build and test scripts, never the
reference patch, the hidden tests or the proofs of concept.

### `build_prompt()`

```python
def build_prompt(metadata: Metadata) -> str
```

Return the task prompt for a task's public metadata.

The prompt names the project and its language, gives fixed instructions, then
every description field that is set (the bug description, the issue and each
report), the source path, and the build and test scripts. A field that is
empty or holds the placeholder `none` is left out.

### `task_prompt()`

```python
def task_prompt() -> str
```

Return the prompt for the task of this container.

It imports `sse.project`, so it needs the daemon.

## `sse.tools.bencher`

The daemon's `bencher` tool: build, test and run proofs of concept on a copy of the source tree.

`sse.project` wraps these functions for agents. The evaluator calls them with
`grading=True` over the daemon's admin socket, which runs every check whatever the difficulty
level. Each function raises `SDKError` when the task does not support the check,
when the daemon refuses it, or when the daemon fails; a check that fails is a result with a
non-zero exit code.

### `build()`

```python
def build(*, grading: bool = False) -> ScriptResult
```

Build the project, and keep the build for `run_poc`.

With `grading`, build the clean copy of the repository that `POST /prepare_grading`
applied the agent's diff to, instead of the source tree the agent edits.

### `run_poc()`

```python
def run_poc(poc, *, grading: bool = False) -> ScriptResult
```

Run the proof of concept `poc` against the last `build`.

Exit code 0 means that the vulnerability no longer triggers; without a build the exit code is
-1. `grading` has no effect: the proof of concept runs in whatever the last build built.

### `function_test()`

```python
def function_test(*, grading: bool = False) -> ScriptResult
```

Run the project's tests on a copy of the source tree, or with `grading` of the graded copy.

### `intent_test()`

```python
def intent_test(*, grading: bool = False) -> ScriptResult
```

Apply the hidden tests of the fix to a copy of the source tree and run the project's tests.

With `grading`, the copy is of the graded repository. Hidden tests that do not apply to the
agent's changes give exit code 1 instead of an error.

## `sse.tools.bash`

The daemon's `bash` tool: one interactive shell in the source tree, as the unprivileged user.

### `execute()`

```python
def execute(command: str) -> ScriptResult
```

Run `command` in the daemon's shell and wait for it to finish.

The shell persists between calls, so `cd` and `export` carry over; `exit` ends it.

## `sse.grading`

Grading module for SSEBench SDK.

Runs all available tests for a benchmark case (based on capabilities)
and returns a structured PatchResult describing what passed and what failed.

### `class PatchResult`

```python
@dataclass
class PatchResult(
    build_success: bool | None = None,
    pov_passed: int | None = None,
    pov_total: int | None = None,
    func_test_success: bool | None = None,
    intent_test_success: bool | None = None,
    error_msg: str | None = None,
    error_log: str | None = None,
)
```

Structured result of grading a patch against all available tests.

Fields are `None` when the corresponding step was not applicable
(e.g. no build script configured).  A `None` value is *not* treated
as a failure by `is_fully_successful`.

| Field | Type | Description |
|---|---|---|
| `build_success` | `bool \| None` | Whether the patched project builds. |
| `pov_passed` | `int \| None` | Number of proofs of concept that no longer trigger the vulnerability. |
| `pov_total` | `int \| None` | Number of proofs of concept run. |
| `func_test_success` | `bool \| None` | Whether the project's tests pass. |
| `intent_test_success` | `bool \| None` | Whether the tests pass with the hidden tests of the fix applied. |
| `error_msg` | `str \| None` | The first failure, such as `Build failed`. |
| `error_log` | `str \| None` | Output of the step that failed first. |

#### `PatchResult.is_fully_successful()`

```python
def is_fully_successful() -> bool
```

Return True when every *executed* step passed.

#### `PatchResult.mark_failure()`

```python
def mark_failure(msg: str, log: str | None = None) -> None
```

Record the *first* failure encountered.

Subsequent calls are no-ops so the original failure context is
preserved while later steps keep running.

### `grade()`

```python
def grade() -> PatchResult
```

Run all available tests and return a `PatchResult`.

The pipeline is driven entirely by the case's capabilities:

1. **Build** -- early-return on failure (everything else depends on it).
2. **Security test** -- runs *all* PoCs, records how many passed.
3. **Function test** -- runs the project's own test suite.
4. **Intent test** -- runs the test suite with the intent patch applied.

Call it over the daemon's admin socket, after the agent has finished: it applies the agent's
diff to the copy of the repository that is graded, and the agent-facing socket refuses that.

Raises `SDKError` on infrastructure failures
(daemon unreachable, etc.) -- those are *not* test failures.

## `sse.reference`

Reference patch access for post-agent tooling (grading, review, web UI).

WARNING: This exposes the reference patch (the answer). It must never be used
by an agent while it works. The daemon serves `/reference/patch` only on its
privileged admin socket or after the agent phase has ended, so a call made
during the agent phase over the agent-facing socket fails.

### `get_reference_patch()`

```python
def get_reference_patch() -> str
```

Return the reference patch as a unified diff string.

Calls the daemon's `/reference/patch` endpoint. Returns an empty string
if no reference patch is configured for the task.

## `sse.helper`

The result type of the daemon's script actions, and the decorator that converts to it.

### `wrap_result()`

```python
def wrap_result[T](
    cls: type[T],
) -> Callable[[Callable[..., Any]], Callable[..., T]]
```

Decorator to wrap daemon results into dataclass instances.

Assumes daemon.py already handles error responses by raising SDKError.
This decorator converts successful JSON responses to the specified class.

### `class ScriptResult`

```python
@dataclass
class ScriptResult(code: int, stdout: str, stderr: str)
```

Result of a script execution.

This represents a successful execution of a script (the script ran).
Check is_success() to see if the script returned exit code 0.

| Field | Type | Description |
|---|---|---|
| `code` | `int` | Exit code of the script. |
| `stdout` | `str` | Standard output of the script. |
| `stderr` | `str` | Standard error of the script. |

#### `ScriptResult.is_success()`

```python
def is_success() -> bool
```

Check if the script returned exit code 0.

## `sse.error`

Error types for SSEBench SDK.

### `class SDKError`

```python
class SDKError(message: str)
```

Subclass of `Exception`.

Raised when the SDK encounters an error from the daemon.

This exception is raised for daemon communication failures, config errors,
file not found, etc. - NOT for script execution failures (non-zero exit code).

Script execution results (success or failure) are returned as ScriptResult.
Use result.is_success() to check if the script succeeded.

## `sse.daemon`

HTTP client of `ssebench-daemon`, which the rest of the SDK goes through.

The client connects to the Unix socket in `SSE_DAEMON_SOCKET`, or, when that is unset, over
TCP to the `host:port` in `SSE_AGENT_DOCKER`. The daemon's HTTP API is described in
docs/reference/daemon-api.md.

### `same_version()`

```python
def same_version(sdk_version: str, daemon_version: object) -> bool
```

Compare the SDK's PEP 440 version with the daemon's SemVer one.

Both come from the same release, spelled per ecosystem (1.0.0rc1 and
1.0.0-rc.1); PEP 440 parsing normalizes the SemVer spelling.

### `class Daemon`

```python
class Daemon()
```

A connection to the daemon.

Creating one asks the daemon for its version and logs a warning when it differs from the
SDK's. Raises `Exception` when neither `SSE_DAEMON_SOCKET` nor `SSE_AGENT_DOCKER` is
set, and `RuntimeError` when the daemon does not answer.

#### `Daemon.get()`

```python
def get(path, headers=None)
```

Send `GET path` and return the JSON body.

Raises `SDKError` with the daemon's message when it answers with an
error status, and on network errors.

#### `Daemon.post()`

```python
def post(path, data, headers=None)
```

Send `POST path` with `data` as the JSON body and return the JSON body of the answer.

Raises `SDKError` as `get` does.

#### `Daemon.prepare_grading()`

```python
def prepare_grading()
```

`POST /prepare_grading`: save the agent's diff and apply it to the copy that is graded.

Only the admin socket accepts it.

#### `Daemon.version()`

```python
def version()
```

`GET /version`: the daemon's version.

#### `Daemon.project()`

```python
def project()
```

`GET /project`: the task's metadata, as `sse.project.Metadata` holds it.

#### `Daemon.capabilities()`

```python
def capabilities()
```

`GET /capabilities`: the checks the task supports.

#### `Daemon.tool()`

```python
def tool(name, action, data)
```

`POST /tool/{name}?action={action}` with `data` as the JSON body.

## `sse.ai`

OpenCode agent wrapper.

Provides a reusable async client for starting an OpenCode server,
creating sessions, sending prompts, and collecting responses.

Usage:

```python
from sse.ai import OpenCodeAgent, build_opencode_config

config = build_opencode_config("claude-sonnet-4-20250514")
async with OpenCodeAgent(directory="/path/to/project", config=config) as agent:
    session_id = await agent.create_session()
    response = await agent.send_prompt(session_id, "hello")
    print(response.final_message)
```

### `class AgentResponse`

```python
@dataclass
class AgentResponse(final_message: str, full_log: str)
```

Structured response from an OpenCode agent session.

| Field | Type | Description |
|---|---|---|
| `final_message` | `str` | Text parts from the last assistant message only. |
| `full_log` | `str` | All text parts from every message in the session. |

### `build_opencode_config()`

```python
def build_opencode_config(
    model_name: str | None = None,
    mcp_url: str | None = None,
) -> dict[str, Any]
```

Build a complete OpenCode config.

When `SSE_MODEL_NAME`, `SSE_BASE_URL` and `SSE_API_KEY` are set, as they are in a task
container, the config uses the run's model through the LiteLLM proxy and ignores
`model_name`. Otherwise it uses `model_name` with OpenCode's built-in Anthropic provider,
which reads the `ANTHROPIC_API_KEY` environment variable at runtime -- the key is **not**
embedded in the config dict.

**Arguments:**

- `model_name`: Anthropic model identifier (e.g. `claude-sonnet-4-20250514`); required when the `SSE_*` variables are not all set.
- `mcp_url`: Optional MCP server URL to register.

**Returns:**

Config dict suitable for the `OPENCODE_CONFIG_CONTENT` env var.

**Raises:**

- `ValueError`: If `model_name` is missing and the `SSE_*` variables are not all set.

### `class OpenCodeAgent`

```python
class OpenCodeAgent(
    directory: str,
    config: dict[str, Any],
    port: int = 4097,
    hostname: str = '127.0.0.1',
)
```

Async wrapper for the OpenCode agent server.

Manages the full lifecycle: start the server, create sessions,
send prompts, collect responses, and shut down cleanly.

With a config that uses OpenCode's built-in Anthropic provider (see
`build_opencode_config`), the Anthropic API key must be available as
the `ANTHROPIC_API_KEY` environment variable in the process that runs
this agent.

Usage:

```python
from sse.ai import OpenCodeAgent, build_opencode_config

config = build_opencode_config("claude-sonnet-4-20250514")
async with OpenCodeAgent(directory="/path/to/project", config=config) as agent:
    session_id = await agent.create_session()
    response = await agent.send_prompt(session_id, "hello")
    print(response)
```

#### `OpenCodeAgent.start()`

```python
async def start(timeout: int = 120) -> None
```

Start the OpenCode server and block until it is ready.

**Arguments:**

- `timeout`: Maximum seconds to wait for server readiness.

**Raises:**

- `RuntimeError`: If the server process exits prematurely.
- `TimeoutError`: If the server does not become ready in time.

#### `OpenCodeAgent.stop()`

```python
async def stop() -> None
```

Shut down the OpenCode server and close the HTTP client.

#### `OpenCodeAgent.create_session()`

```python
async def create_session(title: str = 'Session') -> str
```

Create a new chat session.

**Arguments:**

- `title`: Human-readable session title.

**Returns:**

The session ID string.

**Raises:**

- `httpx.HTTPStatusError`: If session creation fails.

#### `OpenCodeAgent.send_prompt()`

```python
async def send_prompt(
    session_id: str,
    text: str,
    timeout: float = 300.0,
) -> AgentResponse
```

Send a prompt and wait for the complete response.

Uses the synchronous `POST /session/:id/message` endpoint which
blocks until the assistant finishes responding.  After receiving the
response, all session messages are fetched to build the full
conversation log.

**Arguments:**

- `session_id`: Target session ID (from `create_session`).
- `text`: The prompt text.
- `timeout`: Maximum seconds to wait for the assistant to finish. If exceeded, `final_message` will contain a timeout indicator and `full_log` will contain whatever messages were available at that point.

**Returns:**

An `AgentResponse` containing the final assistant message text (or a timeout indicator) and the full conversation log.

**Raises:**

- `httpx.HTTPStatusError`: On HTTP-level failures from the server.

<!-- end generated -->
