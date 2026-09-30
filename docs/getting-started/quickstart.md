---
outline: deep
---

# Quickstart

This page gets you from nothing to a graded run. Every path runs the pilot task
`gjson-196-bf4efcb`, a Go task that builds in seconds, and every path assumes
Docker and [uv](https://docs.astral.sh/uv/) are installed; see
[Installation](/getting-started/installation).

| You want to | You need | Go to |
|---|---|---|
| See a graded run in the web UI, with no key and no model | a clone, [just](https://just.systems/) | [Five minutes: `just demo`](#five-minutes-just-demo) |
| Run a real agent on a task | a clone and the key of a model provider | [Run an agent with your own key](#run-an-agent-with-your-own-key) |
| Do the same without cloning the repository | the key of a model provider | [Without a clone](#without-a-clone) |

Then [read the results](#read-the-results).

## Five minutes: `just demo`

```sh
git clone https://github.com/42-b3yond-6ug/ssebench.git
cd ssebench
just setup
just demo
```

`just setup` installs the dependencies and writes `.env` with generated local
secrets. `just demo` checks your host, gets the images, starts the
[LiteLLM proxy](/concepts/litellm-proxy), the task catalog and the
[web UI](/webui/), and runs the [`reference` agent](/reference/cli#reference-runs)
on `gjson-196-bf4efcb`. The reference agent applies the task's known upstream
fix instead of asking a model for one, so the demo needs no API key, and every
check passes. With the images cached, it ends with:

```text
Done in 45s (images 2s, stack 12s, run 30s).
Result:  build passed, PoC 1/1 passed, functional tests passed, intent tests passed

Open http://127.0.0.1:3001
The run gjson-196-bf4efcb / reference is listed there, with its dialog, diff and evaluation result.
```

Open `http://127.0.0.1:3001` and click the run in the list on the left. The
**Agent Dialog** shows what the agent did, **Changes** the diff against the
vulnerable commit, and **Evaluation Result** the grade; see
[Watching a run](/webui/run-view). When you are done:

```sh
just demo-down
```

This removes what the demo created: its containers, its Compose project and the
database volume. The images stay cached, and the run's files stay in `results/`.

The first run pulls or builds about 4 GB of images. [Try the demo](/getting-started/demo)
has the timings, the settings (ports, the Compose project) and what to do when
it stops early.

## Run an agent with your own key

A real agent calls a model with your key, which **costs money**. It works until
it stops or reaches the timeout (one hour by default, `--timeout` changes it),
so start with a small task like this one.

From a clone that you have set up with `just setup`:

1. Put the key of your model provider in `.env`:

   ```sh
   ANTHROPIC_API_KEY=sk-ant-...
   ```

   The variables are `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and
   `GOOGLE_API_KEY`. The proxy reads provider keys from `.env` only, not from
   your shell.

2. Check the setup. The `Provider keys` line names the keys that are set:

   ```sh
   just doctor
   ```

3. Run the task:

   ```sh
   just run --task gjson-196-bf4efcb --agent claude-code --model claude-sonnet-4-6
   ```

`just run` passes its arguments to `ssebench run` and adds
`--local datasets/pilot`, so it is the same as:

```sh
uv run ssebench run --local datasets/pilot --task gjson-196-bf4efcb --agent claude-code --model claude-sonnet-4-6
```

`ssebench run` starts the LiteLLM proxy if it is not running, builds the case,
tool and agent [image layers](/concepts/image-layers), runs the agent in the
task container and then grades what it left behind. The first run of a task
takes a few minutes for the images. Names come from these places:

| What | Where | List them |
|---|---|---|
| Task | `datasets/pilot/<task-id>/` | `uv run ssebench tasks list` |
| Agent | `agents/<name>/` | `claude-code`, `codex`, `opencode`, `dummy`, `reference` |
| Model | `models/*.yaml` | `grep -h model_name models/*.yaml` |

Without arguments, `just run` opens fzf pickers for the task, the model, the
agent and the mode. `just run-all --agent <agent> --model <model>` runs every
pilot task, one after the other. [CLI](/reference/cli) lists every option;
`--difficulty` sets how much the agent may check while it works, see
[Difficulty levels](/concepts/difficulty-levels).

::: tip Pull the case image instead of building it
`--local` builds the task's case image from its folder. Without it, `ssebench
run` pulls the prebuilt image of the task, which already holds its base image,
so the base images are not needed:

```sh
uv run ssebench run --task gjson-196-bf4efcb --agent reference
```

That is how `ssebench` runs [without a clone](#without-a-clone). `--build`
builds the case image from the task's folder even though a prebuilt one exists.
See [Prebuilt images](/dataset/pilot#prebuilt-images) for the tags, the digests
that pin them and the size of every image.
:::

To watch a real run live in the web UI, start it with the demo instead:

```sh
just demo --agent claude-code --model claude-sonnet-4-6
```

It stops before it builds anything when the model's key is missing from `.env`.

::: tip Check the setup without spending anything
`just run --task gjson-196-bf4efcb --agent dummy --model claude-sonnet-4-6`
makes no model calls: the `dummy` agent exits at once, so the evaluator grades
the unmodified source tree and the patch fails. That is expected, and it shows
that your images, proxy and grading work. `--agent reference` without `--model`
applies the known fix and passes.
:::

## Without a clone

You do not need the repository to run a pilot task. The `ssebench` package on
PyPI carries the agent definitions, the model list and the pilot task list;
the task images come from the registry. You need Docker with buildx and
Compose, and uv:

```sh
mkdir ssebench-work && cd ssebench-work
uvx ssebench init
uvx ssebench doctor
uvx ssebench tasks list
uvx ssebench run --task gjson-196-bf4efcb --agent reference
```

`init` writes `.env` with generated secrets, a copy of the model definitions in
`models/` and an empty `results/`. `doctor` checks Docker, disk space and
`.env`. `tasks list` prints the 55 pilot tasks without touching the network.
The `reference` run needs no key.

For a real agent, add your provider key to `./.env` (`ANTHROPIC_API_KEY=...`),
run `uvx ssebench doctor` to see that it is set, and run:

```sh
uvx ssebench run --task gjson-196-bf4efcb --agent claude-code --model claude-sonnet-4-6
```

Run every `ssebench` command from this directory: it holds `.env` and
`models/`, and `results/` is written here. Edit `models/` to add or change a
model; `ssebench run` rebuilds the proxy image when a file changes. The first
run pulls the task's [case image](/dataset/pilot#prebuilt-images) and the
runtime image from the registry, and builds the tool, agent and proxy layers on
your machine, which downloads packages, so it needs network access. `uv tool install ssebench` keeps the
command on your `PATH` instead of running it through `uvx`.

Without a clone there is no `just`: `uvx ssebench proxy up` starts the proxy,
and `uvx ssebench demo up` runs the demo. [CLI](/reference/cli#without-a-clone)
describes what the package carries and what it pulls.

## Read the results

Every run writes to `results/` in the working directory:

```text
results/
├── gjson-196-bf4efcb-reference-none.json      the summary: the grade, the settings, the spend
└── gjson-196-bf4efcb/none/reference/          the run directory: everything the container produced
    ├── result.json                            the grade
    ├── dialog.jsonl                           the agent's session
    ├── final.patch                            the patch that was graded
    ├── source.tar.gz                          the source tree after grading
    └── agent.log  daemon.log  mcp.log  evaluator.log  …
```

The run directory is `results/<task>/<model>/<agent>/`. A reference run has the
model `none`; the run of `claude-code` above writes
`results/gjson-196-bf4efcb/claude-sonnet-4-6/claude-code/` and
`results/gjson-196-bf4efcb-claude-code-claude-sonnet-4-6.json`. Running the same
combination again replaces the earlier results, so move them first to keep
them.

`result.json` is the evaluator's grade:

```sh
jq .patch_result results/gjson-196-bf4efcb/none/reference/result.json
```

```json
{
  "status": "passed",
  "build_success": true,
  "pov_passed": 1,
  "pov_total": 1,
  "func_test_success": true,
  "intent_test_success": true,
  "error_msg": null,
  "error_log": null
}
```

| Field | Meaning |
|---|---|
| `status` | `passed` when every check that ran passed, `failed` when a check failed or the patch did not apply, `error` when nothing could be graded. |
| `build_success` | The patched project builds. |
| `pov_passed`, `pov_total` | How many of the task's proof-of-concept inputs no longer trigger the vulnerability. |
| `func_test_success` | The project's own tests pass. |
| `intent_test_success` | The tests that came with the upstream fix pass. |
| `error_msg`, `error_log` | The first check that failed, and its output. |

A check that did not run, because the task does not have it or an earlier
failure ended grading, is `null`. `runtime_result` records how long the agent ran
and whether it timed out. The summary adds the run settings as `config` and what
the model calls cost as `spend`, in US dollars. [Results format](/concepts/results)
describes every file, and [Grading pipeline](/concepts/grading) how to read a
grade.

::: tip A `failed` grade that came too quickly
When the agent never got to work, for example because its provider key is missing
or invalid, the run still ends with a grade: `failed`, with the proof of concept
of the untouched source tree as `error_msg`, and a `spend` of 0. Look at
`agent.log` in the run directory, and see [Troubleshooting](/getting-started/troubleshooting#the-agent-ended-at-once-or-said-it-could-not-log-in).
:::

After `just demo`, the run's container is still alive for the web UI, so its
`result.json` has no `config` yet, and the summary is not written, until
`just demo-down` removes the container.

`just report` combines the summaries in `results/` into a PDF report; it needs
jq and [Typst](https://typst.app/). It leaves reference runs out of the scores.

## Next steps

- [Troubleshooting](/getting-started/troubleshooting): what `ssebench doctor` reports and how to fix it
- [Web UI](/webui/): launch runs and watch them live
- [Architecture](/concepts/architecture): what happens during a run
- [Add a model](/guides/add-a-model): use another provider or model
- [The pilot dataset](/dataset/pilot): the tasks you can run
