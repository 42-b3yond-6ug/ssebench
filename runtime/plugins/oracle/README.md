# Oracle plugin

Generates material for a human to build a *deterministic oracle* for a task: an
extra check, independent of LLM reasoning, that a future run can use to grade a
patch. It runs the run's model to compare the agent's patch against the
reference patch, and can optionally try to fuzz the patched project.

The plugin **does not affect grading**. Its output is for human review; a
generated oracle is only added to a task after a person has checked it.

## When it runs

At `after-grading`: the agent has finished, so the reference patch is available
to post-agent tooling, and the plugin runs as root next to the evaluator. It
reads the agent's patch (`final.patch`) from the daemon's admin socket, since git
refuses to run as root in the agent's repository. It writes its outputs under
`oracle/` in the results directory:

- `review.txt` — the model's comparison of the agent's patch and the reference;
- `ai_review_dialog.txt` — the full review session.

## Requirements

- **A model.** The plugin declares `llm: true`, so it receives the run's
  `SSE_API_KEY`, `SSE_BASE_URL` and `SSE_MODEL_NAME`. Without them it logs a
  warning and exits without doing anything, so it is disabled by default.
- **OpenCode**, which the sandbox tool image already includes.
- **Fuzzing is opt-in.** Set `SSE_ORACLE_FUZZ=1` to run the fuzzing stage after
  the review. It installs and runs AFL++, so the run needs `--egress open`.
  Without it, only the review runs, which needs no internet.

## Enabling it

```sh
ssebench run --plugin oracle --egress open ...   # with fuzzing: also SSE_ORACLE_FUZZ=1
```

or set `enabled: true` in `runtime/plugins/plugins.yaml`. It is experimental,
and its APIs (and the SDK's AI helpers) are not stable.
