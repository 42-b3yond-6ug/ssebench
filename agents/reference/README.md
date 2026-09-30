# reference

The `reference` agent applies the task's reference patch, the known upstream
fix, to the project source and exits. The evaluator then grades that fix like
any agent's patch. A reference run makes no model calls and needs no provider
key:

```sh
uv run ssebench run --local datasets/pilot --task gjson-196-bf4efcb --agent reference
```

On a sound task it passes every check the task has: the build, the proofs of
concept, the functional tests and the intent tests. That makes it the positive
check for a task (the `dummy` agent, which changes nothing, is the negative
one) and a demo that costs nothing.

## How it gets the patch

`ssebench run` copies the file named by `files.patch` in the task config out
of the case image and bind-mounts it read-only at `/reference/patch.diff`, for
this agent only. The agent finds the source directory through the SDK
(`sse.project.source`), like the other agents, applies the patch with
`git apply` (or `patch -p1` when it needs fuzz) and stages the result, so the
files the patch adds are part of the graded diff. Everything else follows the
integrity rules of every run: the agent runs as `model`, `/ssebench` is out of
its reach, and the daemon withholds `GET /reference/patch` until the agent
phase ends.

## How the results are labelled

A reference run grades the task, not a model, so it is never counted as a
model's score:

- the run records the model as `none`, so its results go to
  `results/<task>/none/reference/<run-id>/`, with no spend;
- `result.json` and the summary have `config.agent: "reference"` and
  `config.reference_run: true`;
- the container carries the label `ssebench.reference-run=true`, and the web
  UI marks its evaluation result as a reference run;
- `just report` leaves reference runs out of the scores.

`--model` is optional with this agent. A model other than `none` is ignored,
with a warning. The run still starts the LiteLLM proxy, whose network the
container joins like any run's.
