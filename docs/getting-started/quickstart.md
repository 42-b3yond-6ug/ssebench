---
outline: deep
---

# Quickstart

This page runs one agent on one task from the [pilot dataset](/dataset/pilot).
It assumes you have followed [Installation](/getting-started/installation) and
are in the repository root.

## 1. Build the base images

```sh
just base-images
```

This builds the C, Go and Rust toolchain images that every pilot task builds
on. To build only the one you need, name it:

```sh
make -C images/base-images generic-go   # or generic-c, generic-rust
```

## 2. Start the LiteLLM proxy

```sh
just launch
```

This builds the proxy image with the models defined in `models/` and starts it,
together with its Postgres database, as the
[local Docker Compose stack](/deployment/compose). The proxy listens on port
4000:

```sh
curl http://localhost:4000/health/liveliness
```

`ssebench run` also starts the proxy when it is not running, but it does not
rebuild it. Run `just launch` again after you change anything in `models/`.

## 3. Run a task

```sh
uv run ssebench run \
    --local datasets/pilot \
    --task gjson-196-bf4efcb \
    --agent claude-code \
    --model claude-sonnet-4-6
```

`gjson-196-bf4efcb` is a Go task, so it needs only the Go base image. The first
run of a task builds its case, tool and agent images, which takes a while. The
agent then works until it stops or reaches the timeout (one hour by default),
and the evaluator grades what it left behind.

Model names come from `models/*.yaml` and agent names from `agents/`. The
[CLI reference](/reference/cli) lists every option.

::: tip
Use `--agent dummy` to check your setup without an API key. The `dummy` agent
exits immediately and makes no model calls, so the evaluator grades the
unmodified source tree and the patch fails. That is expected.
:::

## Results

Each run writes to `results/<task>/<model>/<agent>/`:

- `result.json`: the evaluator's grade;
- `dialog.jsonl`: the agent's session, in the
  [dialog protocol](/reference/dialog-protocol) format;
- a snapshot of the final source tree, and the logs of every component.

A summary of the run, with the grade, the run settings and what the model
spent, is written to `results/<task>-<agent>-<model>.json`. `just report`
combines the summaries in `results/` into a PDF report; it needs jq and Typst.

See [Results format](/concepts/results) for the details.

## Next steps

- [Web UI](/webui/): launch runs and watch them live
- [Architecture](/concepts/architecture): what happens during a run
- [Add a model](/guides/add-a-model): use another provider or model
