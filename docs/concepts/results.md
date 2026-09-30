---
outline: deep
---

# Results format

Every `ssebench run` writes a **run directory** of its own under `results/` in
the working directory. It holds everything the container produced, and the
**summary**, which combines the grade with the run's settings and cost.

```
results/
└── <task>/<model>/<agent>/
    ├── latest -> <run-id>               link to the newest run directory
    └── <run-id>/                        the run directory (root-only inside the container)
        ├── summary.json                 the summary
        ├── result.json                  the grade
        ├── final.patch                  the agent's changes
        ├── commits.log                  the agent's commit messages
        ├── source.tar.gz                the agent's source tree
        ├── reference.patch              the reference patch (added after the run, if the task has one)
        ├── agent.log  daemon.log  mcp.log  evaluator.log  opencode.log
        ├── scriptrunner-<ms>.log        one per script the daemon ran
        ├── patch-<ms>.log               one per test diff the daemon applied
        ├── plugins/                     plugin logs and outcomes, when plugins ran
        └── archive/                     the agent's own directory (SSE_ARCHIVE)
            └── dialog.jsonl             the agent's session
```

A run of the `dummy` agent on `gjson-196-bf4efcb` with `claude-sonnet-4-6`
writes `results/gjson-196-bf4efcb/claude-sonnet-4-6/dummy/<run-id>/`. A
[reference run](#reference-runs) has the model `none`.

## Run IDs and repeated runs

Every run has an ID, which is the name of its run directory and the value of
the `ssebench.run-id` label on its containers. `--run-id` sets it, with 1 to 64
letters, digits, `.`, `_` or `-`, and not `latest`. Without it, the CLI makes
one from the UTC time the command started and six random hex digits, such as
`20260929-153012-a1b2c3`; such IDs sort in the order the commands started.

A run never writes into a directory that exists, so results are never replaced:
`ssebench run --run-id <id>` with an ID that the task, model and agent already
used stops before it starts anything. Run the same command again for another
trial, or start several at once:

```bash
for trial in 1 2 3; do
  uv run ssebench run --local datasets/pilot --task gjson-196-bf4efcb \
    --agent claude-code --model claude-sonnet-4-6 --run-id "trial-$trial"
done
```

`latest`, beside the run directories, is a relative symbolic link to the run
that started last, finished or not, so
`results/<task>/<model>/<agent>/latest/result.json` is the grade of the newest
run. The CLI replaces it when a run starts. It is outside the run directories,
which the container writes as root, so you can also move or delete it as
yourself; nothing reads it but you. If the file system has no symbolic links,
the run goes on without it.

## The run directory

The CLI mounts the run directory into the container root-only, at `SSE_RESULTS`
(`/var/lib/ssebench/results`), and its `archive/` subdirectory as the agent's
`SSE_ARCHIVE` (`/tmp/sse-archive`). Root writes the grade and the logs; the
agent writes only inside `archive/`, so a file it plants there cannot redirect
a root write. The CLI writes `summary.json` when the container exits, so the
`artifact` plugin's manifest does not list it.

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
    "evaluator_timeout": false,
    "agent_exit_code": 0
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
| `patch_result.status` | string | The verdict: `passed` when every check that ran passed, `failed` when a check failed or the patch did not apply, `error` when the patch was not graded because no check ran, or the agent failed and the model answered no call. See [Grading pipeline](/concepts/grading#the-result). |
| `patch_result.build_success` | bool or null | The patched project built. |
| `patch_result.pov_passed` | int or null | Proofs of concept that no longer trigger the vulnerability. |
| `patch_result.pov_total` | int or null | Proofs of concept the task has. |
| `patch_result.func_test_success` | bool or null | The project's own tests passed. |
| `patch_result.intent_test_success` | bool or null | The tests of the upstream fix passed. |
| `patch_result.error_msg` | string or null | The first failure: `Build failed`, `PoC failed: <poc>`, `Function test failed`, `Intent test failed` or `Patch apply failed`; or, with `status` `error`, why the run was not graded or says nothing about the model: `Timeout (<n>s)`, `Exception: <message>`, `No check ran` or `The agent exited with status <n> and the model answered no call ...`. |
| `patch_result.error_log` | string or null | The output of the check that failed first. |
| `runtime_result.agent_duration` | int | Seconds the agent ran. |
| `runtime_result.agent_timeout` | bool | The agent reached `--timeout` and was stopped. |
| `runtime_result.agent_exit_code` | int or null | The agent's exit status, 124 after a timeout. `null` when the container did not record one, as with a runtime that predates the field. |
| `runtime_result.evaluator_timeout` | bool | Grading did not finish within the time limit. |
| `config` | object | The run settings, as in the [summary](#the-summary). |

`null` means the check did not run: the task does not have it, or an earlier
failure (a failed build, or a patch that did not apply) ended grading. See
[Grading pipeline](/concepts/grading#the-result) for how to read a result.

While a container runs, the web UI reads the evaluator's document, without
`config`, from the daemon's `GET /result`.

## The summary

When the container exits, the CLI writes `summary.json` in the run directory.
Its `patch_result` and `runtime_result` are copied from `result.json`; the rest
comes from the CLI. For the dummy run (the task config shortened):

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
  "spend": 0.0,
  "run_id": "20260929-153012-a1b2c3",
  "started_at": "2026-09-29T15:30:12.418613Z"
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
| `run_id` | The run's ID, the name of its directory. |
| `started_at` | When the run's container was started, in UTC. It orders the runs of one task, model and agent; [the report](#reports) takes the latest. |

When the container leaves `result.json` empty, for example because it failed to
start, the CLI still writes it and the summary, with `status` `error`, every
check `null`, `error_msg` set to `No result: evaluator did not produce output`,
and `agent_duration` 0. When `result.json` has no `status`, as from an
evaluator that predates the field, the CLI derives it from the checks in the
same way.

The CLI also sets `status` to `error`, keeping the checks as graded, when the
agent exited non-zero (`runtime_result.agent_exit_code`) and the proxy booked no
spend for the run: the model never answered, for example because the provider
key is invalid, and the grade is that of the unmodified project. `error_msg`
says so. Because the proxy books spend in batches, the CLI waits up to 15
seconds for it before it decides. A model without prices in `models/` always
shows a spend of 0, so give it `input_cost_per_token` and `output_cost_per_token`
for this check to work.

## Reference runs

A run of the `reference` agent grades the task's known fix instead of a
model's patch; see [Reference runs](/reference/cli#reference-runs). Its grade
rates the task and the grader, so the results say so wherever they go:

- `config.agent` is `reference` and `config.reference_run` is `true`, in
  `result.json` and in the summary;
- the model is `none` and the spend 0, so the results are in
  `results/<task>/none/reference/<run-id>/`;
- the container carries the label `ssebench.reference-run=true`, and the web
  UI marks its evaluation result as a reference run;
- `just report` leaves reference runs out of the scores.

## Reports

`just report` collects the `summary.json` of the runs in `results/` and builds a
PDF report with Typst (`tools/report/`; it needs Typst). For each agent and
model it shows the average spend and time, and the share of runs that built,
stopped every proof of concept, passed the functional tests and passed the
intent tests, followed by a table of every task. It leaves
[reference runs](#reference-runs) out and says how many it left out. It also
leaves out runs with `status` `error`, which were not graded or never got an
answer from the model, and lists them, since they say nothing about the model.
`just report anonymous` replaces the task IDs with short hashes.

A task, model and agent can have many runs, so the report needs a rule for
which it counts:

- **The latest run** is the default. For each task, model and agent, the run
  with the latest `started_at` counts; a tie goes to the later run ID, and a
  summary without `started_at` counts as older than any that has one. Earlier
  trials are left out, and the command says how many.
- **Every run** with `just report default all`. Each run is a sample of its own,
  so the percentages are shares of runs, and a task that ran more than once has
  a row for each run, numbered `#1`, `#2`, ... from the earliest.

`tools/report/collect.py` applies the rule and writes the JSON that the
report reads (`--runs latest|all`, `--results`, `--output`).

The report reads only `<task>/<model>/<agent>/<run-id>/summary.json`, and only
where the summary's own task, model and agent match the directories it is in.
A run directory without a summary, from a run that is still going or was
killed, is not a run yet.

## Results of earlier versions

Before run directories, a run wrote its files straight into
`results/<task>/<model>/<agent>/` and its summary to
`results/<task>-<agent>-<model>.json`, replacing those of the run before. The
tools do not read that layout:

- `just report` ignores the old summaries, and says how many;
- `ssebench dataset verify` runs into a directory of its own;
- the web UI still shows the grade of a container that was started with the old
  layout, because it reads the directory that the container's
  `ssebench.results` label names.

To bring an old run into a report, move its summary to
`results/<task>/<model>/<agent>/<run-id>/summary.json`. A summary without
`started_at` counts as older than any run that has one.

## Next steps

- [Grading pipeline](/concepts/grading): how the grade is produced
- [Dialog protocol](/reference/dialog-protocol): the format of `dialog.jsonl`
- [Add an agent](/guides/add-an-agent): write an agent that produces these
  files
- [Web UI](/webui/): watch a run and its results live
