---
outline: [2, 3]
---

# Daemon HTTP API

`ssebench-daemon` runs in every task container. It knows the task: the project's
source tree, the build, run and test scripts, and the reference material. The
[Python SDK](/reference/python-sdk), the [MCP server](/reference/mcp-server),
the evaluator and the [web UI](/webui/) use it to read the task, to build and
test the project, and to grade the patch. Agents normally use it through the
SDK or the MCP server's `test_patch` tool.

Every request and response body is JSON. The API is described in OpenAPI 3.1 in
[`sdk/daemon/openapi.yaml`](https://github.com/42-b3yond-6ug/ssebench/blob/main/sdk/daemon/openapi.yaml),
which a test in the daemon's crate checks against the routes it serves, their
access rules and their responses; the tables on this page are generated from
it. Errors have the body `{"error": "<message>"}`.

<!-- The endpoint, gate and schema sections are generated from
sdk/daemon/openapi.yaml by tools/docs/reference.py; edit the YAML, then run
`just docs-gen`. -->

## Listeners

The daemon serves the same routes on up to three listeners. Only the admin
socket is privileged.

| Listener | Address | Used by |
|----------|---------|---------|
| Agent-facing Unix socket | `SSE_DAEMON_SOCKET`, `/tmp/sse.sock` in sandbox mode; mode `0666` | the agent, the SDK in the agent's process, the MCP server |
| Agent-facing HTTP | port `SSE_HTTP_PORT` (`4263`) on all interfaces | the web UI, from the host |
| Admin Unix socket | `SSE_ADMIN_SOCKET`, `/run/ssebench/admin.sock` in sandbox mode; mode `0600`, root only | the entrypoint and the evaluator |

The daemon binds the admin socket only when `SSE_ADMIN_SOCKET` is set, and the
Unix socket only when `SSE_DAEMON_SOCKET` is set; without the latter it serves
HTTP alone. The entrypoint sets both; see
[Environment variables](/reference/environment#inside-the-task-container).

The agent runs as the unprivileged user `model`, so it reaches the agent-facing
listeners but not the admin socket. The daemon enforces the rules that keep the
answer from the agent on the agent-facing listeners, whatever client calls it;
the [integrity model](/concepts/integrity) explains why:

- **Difficulty gate.** The daemon reads `SSE_DIFFICULTY` when it starts and
  answers `403` to the `bencher` actions that the level withholds; see
  [Difficulty gate](#difficulty-gate). The MCP server applies the same levels
  to `test_patch`.
- **Admin-only endpoints.** `POST /prepare_grading` and
  `POST /admin/agent_exited` answer `403`.
- **Reference patch.** `GET /reference/patch` answers `403` until the agent
  phase ends: the entrypoint calls `POST /admin/agent_exited` on the admin
  socket when the agent process exits, and from then on the agent-facing
  listeners serve the patch, which is how the web UI shows it after a run.

The admin socket is never gated, so grading runs every check the task has. The
evaluator's SDK talks to it because the entrypoint points the evaluator's
`SSE_DAEMON_SOCKET` at the admin socket. Post-agent tooling reads the reference
patch with [`sse.reference.get_reference_patch()`](/reference/python-sdk#sse-reference).

## Endpoints

<!-- generated: daemon endpoints -->

| Endpoint | Served on | Summary |
|---|---|---|
| [`GET /version`](#get-version) | every listener | The daemon's version. |
| [`GET /project`](#get-project) | every listener | The task's metadata, without the reference material. |
| [`GET /capabilities`](#get-capabilities) | every listener | Which checks the task supports. |
| [`POST /tool/{name}`](#post-tool-name) | every listener | Run an action of a tool. |
| [`GET /diff`](#get-diff) | every listener | The agent's changes so far, as a unified diff. |
| [`GET /files`](#get-files) | every listener | The files the agent changed, with line counts. |
| [`GET /agent/dialog`](#get-agent-dialog) | every listener | The agent's dialog, from `$SSE_ARCHIVE/dialog.jsonl`. |
| [`GET /result`](#get-result) | every listener | The grade, once the evaluator has written it. |
| [`POST /prepare_grading`](#post-prepare-grading) | admin socket only | Save the agent's diff and apply it to the copy of the repository that is graded. |
| [`GET /final_diff`](#get-final-diff) | every listener | The agent's diff that `POST /prepare_grading` saved. |
| [`POST /admin/agent_exited`](#post-admin-agent-exited) | admin socket only | End the agent phase. |
| [`GET /reference/patch`](#get-reference-patch) | admin socket; agent-facing listeners after the agent exits | The reference patch, the answer to the task. |

<!-- end generated -->

## Difficulty gate

<!-- generated: daemon gate -->

The `bencher` actions of [`POST /tool/{name}`](#post-tool-name) on the agent-facing listeners, by difficulty level:

| Level | `build` | `function_test` | `run_poc` | `intent_test` |
|---|---|---|---|---|
| 0 `FULL_ASSISTANCE` | runs | runs | runs | runs |
| 1 `NO_INTENT_TEST` | runs | runs | runs | 403 |
| 2 `NO_FUTURE_TEST` | runs | runs | 403 | 403 |
| 3 `BUILD_ONLY` | runs | 403 | 403 | 403 |
| 4 `NO_BUILD` | 403 | 403 | 403 | 403 |

<!-- end generated -->

The admin socket runs every action at every level. `bash` is never gated. See
[Difficulty levels](/concepts/difficulty-levels) for what the levels mean to
the agent.

## Agent-facing endpoints

These endpoints answer on every listener.

<!-- generated: daemon agent-facing -->

### `GET /version`

The daemon's version.

The SDK compares it with its own version and warns when they differ.

Served on: every listener.

| Status | Body | Description |
|---|---|---|
| `200` | [Version](#version) | The version. |

### `GET /project`

The task's metadata, without the reference material.

The task config, with the contents of the report files and of the build and test scripts instead of their paths. The reference patch and the hidden tests are left out.

Served on: every listener.

| Status | Body | Description |
|---|---|---|
| `200` | [Metadata](#metadata) | The task's metadata. |

### `GET /capabilities`

Which checks the task supports.

Derived from the scripts and files the task config names. The difficulty level can still withhold a supported check from the agent.

Served on: every listener.

| Status | Body | Description |
|---|---|---|
| `200` | [Capabilities](#capabilities) | The task's capabilities. |

### `POST /tool/{name}`

Run an action of a tool.

`bencher` builds and tests a copy of the source tree; `bash` runs a command in one interactive shell in the source tree, as the unprivileged user `model`. The daemon runs one action at a time. A script that runs and fails is a 200 with a non-zero `code`.

Served on: every listener.

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `name` | path | `bencher` \| `bash` | yes | The tool. |
| `action` | query | `string` | yes | The action: `build`, `run_poc`, `function_test` or `intent_test` for `bencher`. `bash` has one action and ignores the value; the SDK sends `execute`. |

Request body (`application/json`): [GradingArgument](#gradingargument) \| [PocArgument](#pocargument) \| [BashArgument](#bashargument). The action's argument, sent with `Content-Type: application/json`.

| Status | Body | Description |
|---|---|---|
| `200` | [ScriptResult](#scriptresult) | The action ran; its script's exit code and output. |
| `400` |  | The `action` parameter is missing, or the body is not JSON. |
| `403` | [Error](#error) | On an agent-facing listener, a `bencher` action that the difficulty level withholds. |
| `500` | [Error](#error) | An unknown tool or action, an invalid argument, a script the task does not have, or hidden tests that do not apply (`git apply failed`). |

### `GET /diff`

The agent's changes so far, as a unified diff.

The diff of the source tree against the task's single initial commit: the committed changes if the agent committed, otherwise the staged and unstaged ones.

Served on: every listener.

| Status | Body | Description |
|---|---|---|
| `200` | [Diff](#diff) | The diff; empty when nothing changed. |
| `500` | [Error](#error) | git failed. |

### `GET /files`

The files the agent changed, with line counts.

Served on: every listener.

| Status | Body | Description |
|---|---|---|
| `200` | [Files](#files) | The changed files, from `git status`. |
| `500` | [Error](#error) | git failed. |

### `GET /agent/dialog`

The agent's dialog, from `$SSE_ARCHIVE/dialog.jsonl`.

The entries the agent wrote in the dialog protocol. Lines that are not JSON, or have no `seq`, are skipped.

Served on: every listener.

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `since` | query | `integer` | no | Return only the entries whose `seq` is greater, for polling. |

| Status | Body | Description |
|---|---|---|
| `200` | [Dialog](#dialog) | The entries in file order; none when the file does not exist. |
| `500` | [Error](#error) | The file exists but cannot be read. |

### `GET /result`

The grade, once the evaluator has written it.

Served on: every listener.

| Status | Body | Description |
|---|---|---|
| `200` | [EvaluationResult](#evaluationresult) | The grade, or `available: false` before the evaluator has written it or when it cannot be parsed. |

### `GET /final_diff`

The agent's diff that `POST /prepare_grading` saved.

Served on: every listener.

| Status | Body | Description |
|---|---|---|
| `200` | [Diff](#diff) | The saved diff; empty before grading. |
| `500` | [Error](#error) | The saved diff cannot be read. |

<!-- end generated -->

## Admin endpoints

These endpoints answer on the admin socket. The agent-facing listeners refuse
them with `403`, except `GET /reference/patch` after the agent phase.

<!-- generated: daemon admin -->

### `POST /prepare_grading`

Save the agent's diff and apply it to the copy of the repository that is graded.

Writes the agent's diff to `$SSE_ARCHIVE/final.patch` and its commit messages to `$SSE_ARCHIVE/commits.log`, then applies the diff to the clean clone of the repository in `$SSE_REPO_PATH`, which the `bencher` actions use with `grading: true`. The evaluator calls it once, after the agent has finished.

Served on: admin socket only.

| Status | Body | Description |
|---|---|---|
| `200` | [Success](#success) | The diff is saved and applied. |
| `403` | [Error](#error) | The request came from an agent-facing listener. |
| `500` | [Error](#error) | git failed, or the diff does not apply (`git apply failed`). |

### `POST /admin/agent_exited`

End the agent phase.

The entrypoint calls it once the agent process has exited. From then on the agent-facing listeners serve `GET /reference/patch`, so that the web UI can show it. Calling it again has no effect.

Served on: admin socket only.

| Status | Body | Description |
|---|---|---|
| `200` | [Success](#success) | The agent phase has ended. |
| `403` | [Error](#error) | The request came from an agent-facing listener. |

### `GET /reference/patch`

The reference patch, the answer to the task.

The upstream fix that the task config names as `files.patch`. It must never reach the agent while it works, so the agent-facing listeners refuse it until the agent phase has ended.

Served on: admin socket; agent-facing listeners after the agent exits.

| Status | Body | Description |
|---|---|---|
| `200` | [Diff](#diff) | The patch; empty when the task has none or it cannot be read. |
| `403` | [Error](#error) | The request came from an agent-facing listener while the agent works. |

<!-- end generated -->

## Schemas

<!-- generated: daemon schemas -->

### Version

| Field | Type | Required | Description |
|---|---|---|---|
| `version` | `string` | yes | The daemon's version, which is the SSEBench version. |

### Metadata

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `string` | yes | Task ID. |
| `project` | `string` | yes | Name of the upstream project. |
| `language` | `string` | yes | Language of the project, such as `c`, `go` or `rust`. |
| `source` | `string` | yes | Absolute path of the source tree that the agent edits. |
| `task_description` | [TaskDescription](#taskdescription) | yes |  |
| `poc` | array of `string` | yes | Absolute paths of the proof-of-concept inputs, to pass to `run_poc`. |
| `build_script` | `string` \| `null` | yes | Contents of the build script. |
| `test_script` | `string` \| `null` | yes | Contents of the test script. |

### TaskDescription

| Field | Type | Required | Description |
|---|---|---|---|
| `issue` | `string` \| `null` | yes | Issue text. |
| `crash_report` | array of `string` \| `null` | yes | Contents of the report files. |
| `bug_description` | `string` \| `null` | yes | Short description of the bug. |

### Capabilities

| Field | Type | Required | Description |
|---|---|---|---|
| `can_build` | `boolean` | yes | The task has a build script. |
| `can_run_poc` | `boolean` | yes | The task has a run script and at least one proof of concept. |
| `poc_count` | `integer` | yes | Number of proofs of concept. |
| `has_function_test` | `boolean` | yes | The task has a test script. |
| `has_intent_test` | `boolean` | yes | The task has a test script and hidden tests (`files.future_test`). |

### GradingArgument

The argument of `build`, `function_test` and `intent_test`.

| Field | Type | Required | Description |
|---|---|---|---|
| `grading` | `boolean` | no | Use the graded copy of the repository in `$SSE_REPO_PATH` instead of the source tree that the agent edits. Default: `false`. |

### PocArgument

The argument of `run_poc`. It runs in the output of the last `build`.

| Field | Type | Required | Description |
|---|---|---|---|
| `poc` | `string` | yes | Path of the proof of concept, one of `poc` in the metadata. |

### BashArgument

The argument of `bash`.

| Field | Type | Required | Description |
|---|---|---|---|
| `command` | `string` | yes | Shell command. It runs in the persistent shell, so `cd` and `export` carry over to the next command. |

### ScriptResult

| Field | Type | Required | Description |
|---|---|---|---|
| `code` | `integer` | yes | Exit code; -1 for `run_poc` before any `build`. |
| `stdout` | `string` | yes | Standard output. |
| `stderr` | `string` | yes | Standard error. |

### Diff

| Field | Type | Required | Description |
|---|---|---|---|
| `diff` | `string` | yes | Unified diff, with binary changes as git binary patches. |

### Files

| Field | Type | Required | Description |
|---|---|---|---|
| `files` | array of [ChangedFile](#changedfile) | yes |  |

### ChangedFile

| Field | Type | Required | Description |
|---|---|---|---|
| `path` | `string` | yes | Path relative to the source tree. |
| `status` | `modified` \| `added` \| `deleted` \| `renamed` | yes | Untracked files count as `added`. |
| `additions` | `integer` | yes | Lines added. |
| `deletions` | `integer` | yes | Lines deleted. |

### Dialog

| Field | Type | Required | Description |
|---|---|---|---|
| `entries` | array of `object` | yes | Dialog entries, as the dialog protocol defines them. |

### EvaluationResult

| Field | Type | Required | Description |
|---|---|---|---|
| `available` | `boolean` | yes | Whether the evaluator has written the grade. |
| `patch_result` | [PatchResult](#patchresult) | no |  |
| `runtime_result` | [RuntimeResult](#runtimeresult) | no |  |

### PatchResult

The grade; a check the task does not have is `null`.

| Field | Type | Required | Description |
|---|---|---|---|
| `status` | `passed` \| `failed` \| `error` | no | `passed` when every check that ran passed, `failed` when a check failed or the patch did not apply, `error` when no check ran and the patch was not graded. Absent from the results of older evaluators. |
| `build_success` | `boolean` \| `null` | no | Whether the patched project builds. |
| `pov_passed` | `integer` \| `null` | no | Number of proofs of concept that no longer trigger the vulnerability. |
| `pov_total` | `integer` \| `null` | no | Number of proofs of concept run. |
| `func_test_success` | `boolean` \| `null` | no | Whether the project's tests pass. |
| `intent_test_success` | `boolean` \| `null` | no | Whether the tests pass with the hidden tests applied. |
| `error_msg` | `string` \| `null` | no | The first failure, or with `status` `error`, why the patch was not graded. |
| `error_log` | `string` \| `null` | no | Output of the step that failed first. |

### RuntimeResult

| Field | Type | Required | Description |
|---|---|---|---|
| `agent_duration` | `integer` | yes | How long the agent ran, in seconds. |
| `agent_timeout` | `boolean` | yes | Whether the agent hit its time limit. |
| `evaluator_timeout` | `boolean` | yes | Whether grading hit its time limit. |

### Success

| Field | Type | Required | Description |
|---|---|---|---|
| `success` | `true
` | yes |  |

### Error

| Field | Type | Required | Description |
|---|---|---|---|
| `error` | `string` | yes | What went wrong. |

<!-- end generated -->
