# Write a plugin

This guide writes a plugin that records a summary of the agent's patch after
grading, then runs it on a pilot task. [Plugins and hooks](/concepts/plugins-and-hooks)
describes the full contract: the hooks, the users plugins run as, their
environment and how outcomes are recorded. To add a tool layer, a container
mode or a CLI command instead, see [Extension points](/guides/extension-points).

## 1. Create the plugin folder

A plugin is a folder in `runtime/plugins/` named after the plugin, with an
executable `run.sh`. Create `runtime/plugins/diffstat/run.sh`:

```bash
#!/bin/bash
# Summarise the patch that grading applied: files changed, lines added and
# removed.
set -euo pipefail

out="$SSE_ARCHIVE/diffstat"
mkdir -p "$out"
if [ -s "$SSE_RESULTS/final.patch" ]; then
	git apply --stat "$SSE_RESULTS/final.patch" > "$out/diffstat.txt"
else
	echo "no changes" > "$out/diffstat.txt"
fi
```

```sh
chmod +x runtime/plugins/diffstat/run.sh
```

The script runs in its own folder, with the entrypoint's environment:
`SSE_RESULTS` is the results directory, where the daemon wrote `final.patch`
when grading started; it is root-only, so only a grading plugin can read it.
`SSE_ARCHIVE` is the archive directory, where plugins write their output; the
script writes only under `diffstat/` there.

## 2. Register it

Add an entry to `runtime/plugins/plugins.yaml`:

```yaml
- name: diffstat
  enabled: false
  hook: after-grading
  llm: false
  timeout: 2
```

- `hook: after-grading` runs it once the grade is written, as root. A plugin
  that must run during the agent phase uses an `-agent` hook instead and runs
  as the agent's user, `model`.
- `llm: false`: it does not need the run's model, so it does not get the
  model's key.
- `timeout: 2`: if it runs longer than two minutes, it is killed and recorded
  as `timeout`.

`uv run pytest bench/tests/test_plugins.py` checks the file against
`runtime/plugins/schema.json` and that every plugin has its `run.sh`.

## 3. Run it

```sh
uv run ssebench run --local datasets/pilot --task gjson-196-bf4efcb \
  --agent reference --plugin diffstat
```

The [`reference`](/reference/cli#reference-runs) agent applies the task's known
fix and calls no model, so the run needs no key and leaves a patch to summarise.
The CLI installs the plugin in the tool image and enables it for this run. In
the run directory, `results/gjson-196-bf4efcb/none/reference/latest/`:

- `archive/diffstat/diffstat.txt` is the plugin's output;
- `archive/plugins/diffstat.log` has its standard output and error;
- `archive/plugins/results.json` records how it ended:

```json
[
  {
    "name": "diffstat",
    "hook": "after-grading",
    "status": "ok",
    "exit_code": 0,
    "duration_seconds": 0.01,
    "started": true
  }
]
```

The summary, `summary.json` in the run directory, lists it in `config.plugins`
and its outcome in `plugin_results`. `result.json` is the same as without the
plugin.

To run it in every run, set `enabled: true`.

## A plugin in Python

A plugin with a `pyproject.toml` gets its own virtual environment. It is a
member of the repository's uv workspace, so it must be named
`ssebench-plugin-<name>` and listed in `[tool.uv.workspace] members` of the
root `pyproject.toml`; a plugin with only a `run.sh` is not listed there:

```toml
# runtime/plugins/diffstat/pyproject.toml
[project]
name = "ssebench-plugin-diffstat"
version = "1.0.0.dev0"
requires-python = ">=3.12"
dependencies = [
  "ssebench-sdk",
]

[tool.uv.sources]
ssebench-sdk = { workspace = true }
```

Add `"runtime/plugins/diffstat"` to the workspace members and run `uv lock`. The tool layer syncs it into
`/plugins/<name>/.venv`, and `run.sh` starts it with that environment's Python:

```bash
#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
exec .venv/bin/python main.py
```

In `main.py`, the [`sse`](/reference/python-sdk) package reaches the daemon
through `SSE_DAEMON_SOCKET`; after the agent phase, `sse.reference.get_reference_patch()`
returns the reference patch. The Python of these environments is only
readable by root, so Python plugins use the grading hooks.

With `llm: true`, the plugin also gets `SSE_BASE_URL`, `SSE_API_KEY` and
`SSE_MODEL_NAME`, the run's model through the LiteLLM proxy. Check that they
are set and exit with 0 when they are not, as `runtime/plugins/oracle/main.py`
does, so the plugin does nothing without a model instead of failing. Write the
reason to the file named by `SSE_PLUGIN_SKIP_FILE` before you exit, so the run
says that the plugin was [skipped](/concepts/plugins-and-hooks#skipping) and
why.

## Rules

- Never change the grade. Do not write `result.json` or `/sse_result`, and do
  not change the project's source tree before grading has finished.
- In the agent phase, do not give the agent anything it could not reach itself;
  running as `model` already keeps the task files out of reach.
- Write only under `SSE_ARCHIVE`, in a folder named after the plugin.
- Exit with 0 when there is nothing to do, after writing the reason to
  `SSE_PLUGIN_SKIP_FILE`; a non-zero status is recorded as a failure.
