---
outline: deep
---

# Results format

Every `ssebench run` writes two things under `results/` in the working
directory: a **run directory** with everything the container produced, and a
**summary** that combines the grade with the run's settings and cost.

```
results/
├── <task>-<agent>-<model>.json          the summary
└── <task>/<model>/<agent>/              the run directory (root-only inside the container)
    ├── result.json                      the grade
    ├── final.patch                      the agent's changes
    ├── commits.log                      the agent's commit messages
    ├── source.tar.gz                    the agent's source tree
    ├── reference.patch                  the reference patch (added after the run, if the task has one)
    ├── agent.log  daemon.log  mcp.log  evaluator.log  opencode.log
    ├── scriptrunner-<ms>.log            one per script the daemon ran
    ├── patch-<ms>.log                   one per test diff the daemon applied
    ├── plugins/                         plugin logs and outcomes, when plugins ran
    └── archive/                         the agent's own directory (SSE_ARCHIVE)
        └── dialog.jsonl                 the agent's session
```

A run of the `dummy` agent on `gjson-196-bf4efcb` with `claude-sonnet-4-6`
writes `results/gjson-196-bf4efcb-dummy-claude-sonnet-4-6.json` and
`results/gjson-196-bf4efcb/claude-sonnet-4-6/dummy/`. A
[reference run](#reference-runs) has the model `none`.

## The run directory

The CLI mounts the run directory into the container root-only, at `SSE_RESULTS`
(`/var/lib/ssebench/results`), and its `archive/` subdirectory as the agent's
`SSE_ARCHIVE` (`/tmp/sse-archive`). It empties the run directory at the start of
each run. Running the same task, model and agent again replaces the previous
results; move them elsewhere first to keep them. Root writes the grade and the
logs; the agent writes only inside `archive/`, so a file it plants there cannot
redirect a root write.

| File | Written by | Contents |
|---|---|---|
| `result.json` | evaluator, then the CLI | The grade and the run settings; see [below](#result-json). |
| `archive/dialog.jsonl` | the agent's wrapper | The agent's session, one JSON object per line, in the [dialog protocol](/reference/dialog-protocol) format. The web UI renders it. An agent without a wrapper, such as `dummy`, writes none. |
| `final.patch` | daemon, when grading starts | The patch the grader applied, as a git diff; empty when the agent changed nothing. See [Capturing the patch](/concepts/grading#_1-capturing-the-patch). |
| `commits.log` | daemon, when grading starts | Hash, subject and body of each commit the agent made, separated by `---`; empty when it made none. |
| `source.tar.gz` | evaluator | The source tree the agent worked in, as it was after grading. |
| `reference.patch` | the CLI, after the run | The task's reference patch, copied from the task folder when the task has one, for reports and the web UI. |
| `agent.log` | entrypoint | Standard output and error of the agent command. |
| `daemon.log` | entrypoint | The daemon's log, including its difficulty gate and every tool call. |
| `mcp.log` | entrypoint | The MCP server's log, including the difficulty level it read. |
| `evaluator.log` | entrypoint | The evaluator's log, ending with the result it wrote. |
| `opencode.log` | entrypoint | The OpenCode server's log; empty unless the image has OpenCode. |
| `scriptrunner-<ms>.log` | daemon | The command line, exit code, standard output and standard error of one task script, named by the time it started in milliseconds. There is one for each check `test_patch` ran during the run, followed by those of grading. |
| `patch-<ms>.log` | daemon | The result of applying the hidden tests before an intent test. |
| `plugins/<name>.log`, `plugins/results.json` | entrypoint | The output of each [plugin](/concepts/plugins-and-hooks) and how it ended; only when plugins ran. Each plugin writes its own output in a folder named after it, such as `artifact/manifest.json`. |

The MCP server also writes the full log of a long check result to
`/tmp/mcp/logs` inside the container; that directory is not part of the
results.

## `result.json`

The evaluator's grade, written into the root-only results directory when
grading ends. When the container exits, the CLI adds the run settings as
`config`, the same object as in the [summary](#the-summary). The dummy run
above produces:

```json
{
  "patch_result": {
    "status": "failed",
    "build_success": true,
    "pov_passed": 0,
    "pov_total": 1,
    "func_test_success": true,
    "intent_test_success": false,
    "error_msg": "PoC failed: /ssebench/pocs/poc.go",
    "error_log": "panic: runtime error: slice bounds out of range [1:0]\n\ngoroutine 1 [running]:\n..."
  },
  "runtime_result": {
    "agent_duration": 0,
    "agent_timeout": false,
    "evaluator_timeout": false
  },
  "config": {
    "agent": "dummy",
    "model": "claude-sonnet-4-6",
    "…": "…",
    "reference_run": false
  }
}
```

| Field | Type | Meaning |
|---|---|---|
| `patch_result.status` | string | The verdict: `passed` when every check that ran passed, `failed` when a check failed or the patch did not apply, `error` when the patch was not graded because no check ran. See [Grading pipeline](/concepts/grading#the-result). |
| `patch_result.build_success` | bool or null | The patched project built. |
| `patch_result.pov_passed` | int or null | Proofs of concept that no longer trigger the vulnerability. |
| `patch_result.pov_total` | int or null | Proofs of concept the task has. |
| `patch_result.func_test_success` | bool or null | The project's own tests passed. |
| `patch_result.intent_test_success` | bool or null | The tests of the upstream fix passed. |
| `patch_result.error_msg` | string or null | The first failure: `Build failed`, `PoC failed: <poc>`, `Function test failed`, `Intent test failed` or `Patch apply failed`; or, with `status` `error`, why the patch was not graded: `Timeout (<n>s)`, `Exception: <message>` or `No check ran`. |
| `patch_result.error_log` | string or null | The output of the check that failed first. |
| `runtime_result.agent_duration` | int | Seconds the agent ran. |
| `runtime_result.agent_timeout` | bool | The agent reached `--timeout` and was stopped. |
| `runtime_result.evaluator_timeout` | bool | Grading did not finish within the time limit. |
| `config` | object | The run settings, as in the [summary](#the-summary). |

`null` means the check did not run: the task does not have it, or an earlier
failure (a failed build, or a patch that did not apply) ended grading. See
[Grading pipeline](/concepts/grading#the-result) for how to read a result.

While a container runs, the web UI reads the evaluator's document, without
`config`, from the daemon's `GET /result`.

## The summary

When the container exits, the CLI writes
`results/<task>-<agent>-<model>.json`. Its `patch_result` and `runtime_result`
are copied from `result.json`; the rest comes from the CLI. For the dummy run
(the task config shortened):

```json
{
  "task": {
    "id": "gjson-196-bf4efcb",
    "project": "gjson",
    "repository": "https://github.com/tidwall/gjson",
    "language": "go",
    "source": "/src/gjson",
    "…": "…",
    "originality": "public"
  },
  "config": {
    "agent": "dummy",
    "model": "claude-sonnet-4-6",
    "mode": "sandbox",
    "timeout": 3600,
    "difficulty": 2,
    "tool_layer": "sandbox",
    "egress": "restricted",
    "reference_run": false,
    "plugins": []
  },
  "patch_result": { "status": "failed", "build_success": true, "pov_passed": 0, "pov_total": 1, "…": "…" },
  "runtime_result": { "agent_duration": 0, "agent_timeout": false, "evaluator_timeout": false },
  "spend": 0.0
}
```

| Field | Meaning |
|---|---|
| `task` | The task's `config.yaml`, validated, with every key present; see [Dataset manifest](/dataset/manifest#task-config). |
| `config.agent` | Agent name, the directory under `agents/`. |
| `config.model` | Model name, as in `models/*.yaml`. |
| `config.mode` | `sandbox` or `sidecar`. |
| `config.timeout` | The agent's time limit in seconds, `--timeout`. |
| `config.difficulty` | The [difficulty level](/concepts/difficulty-levels), `--difficulty`. |
| `config.tool_layer` | The [tool layer](/concepts/image-layers#tool), `--tool-layer`; `null` in sidecar mode. |
| `config.egress` | The [egress policy](/deployment/integrity-and-egress), `restricted` or `open`. |
| `config.plugins` | The [plugins](/concepts/plugins-and-hooks) enabled for the run, from `--plugin` or `plugins.yaml`; empty when none ran. |
| `config.reference_run` | `true` when the `reference` agent applied the task's known fix; see [Reference runs](#reference-runs). |
| `patch_result`, `runtime_result` | As in `result.json`. |
| `spend` | What the run's model calls cost, in US dollars, as the [LiteLLM proxy](/concepts/litellm-proxy#one-key-per-run) recorded it. |

When the container leaves `result.json` empty, for example because it failed to
start, the CLI still writes it and the summary, with `status` `error`, every
check `null`, `error_msg` set to `No result: evaluator did not produce output`,
and `agent_duration` 0. When `result.json` has no `status`, as from an
evaluator that predates the field, the CLI derives it from the checks in the
same way.

## Reference runs

A run of the `reference` agent grades the task's known fix instead of a
model's patch; see [Reference runs](/reference/cli#reference-runs). Its grade
rates the task and the grader, so the results say so wherever they go:

- `config.agent` is `reference` and `config.reference_run` is `true`, in
  `result.json` and in the summary;
- the model is `none` and the spend 0, so the results are
  `results/<task>-reference-none.json` and `results/<task>/none/reference/`;
- the container carries the label `ssebench.reference-run=true`, and the web
  UI marks its evaluation result as a reference run;
- `just report` leaves reference runs out of the scores.

## Reports

`just report` collects every summary in `results/*.json` and builds a PDF
report with Typst (`tools/report/`; it needs jq and Typst). For each agent and
model it shows the average spend and time, and the share of runs that built,
stopped every proof of concept, passed the functional tests and passed the
intent tests, followed by a table of every task. It leaves
[reference runs](#reference-runs) out and says how many it left out.
`just report anonymous` replaces the task IDs with short hashes.

## Next steps

- [Grading pipeline](/concepts/grading): how the grade is produced
- [Dialog protocol](/reference/dialog-protocol): the format of `dialog.jsonl`
- [Add an agent](/guides/add-an-agent): write an agent that produces these
  files
- [Web UI](/webui/): watch a run and its results live
