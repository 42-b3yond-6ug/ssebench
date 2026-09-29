---
outline: deep
---

# Task prompt

The agent learns about its task from one prompt. The bundled agents,
`claude-code`, `codex` and `opencode`, all send the same prompt, which
`sse.prompt.task_prompt()` in the [Python SDK](/reference/python-sdk) builds
from the task's public metadata. So for a given task, a difference between their
results comes from the agent and the model, not from what they were told.

## What goes in

The prompt is built from the daemon's `GET /project`, the view of the task an
agent is allowed to see (see [What the agent sees](/concepts/tasks-and-datasets#what-the-agent-sees-and-what-it-doesn-t)):

| Section | Content | From the task config |
|---|---|---|
| Task | The role, and the project's name and language | `project`, `language` |
| Objective, Requirements, Validation | Fixed instructions: fix the root cause, keep the project's behaviour, commit the fix, and how the fix is checked | none |
| Vulnerability | Every description field that is set, each under its own heading | `task_description` |
| Project | Name, language and the path of the source tree | `project`, `language`, `source` |
| Build and test | The build script and the test script | `scripts.build`, `scripts.test` |

The Vulnerability section has, in this order:

1. **Bug description**: `task_description.bug_description`;
2. **Issue**: `task_description.issue`;
3. **Report**: the contents of each file in `task_description.crash_report`,
   in the order of the config, numbered `Report 1 of N` when there are
   several, each in a code fence.

A field that is empty, or holds only the placeholder `none`, is left out, and
so is an empty report file. A task with no description left says so in the
section. `ssebench dataset validate` requires at least one of the three fields.

The test script is shown with its call to `/ssebench/scripts/build.sh`, which
the agent cannot read, replaced by a comment; the build script is shown on its
own above it. Code fences are made longer than any run of backticks in what they
hold, so a report in Markdown with its own code blocks stays intact.

The prompt depends on nothing else: the same task gives the same prompt, byte
for byte, in every run.

## What stays out

The prompt never contains material the grader uses to judge the patch:

- the reference patch, `files.patch`;
- the hidden tests, `files.future_test`;
- the proofs of concept, `files.poc`, and the run script that executes them;
- the upstream commits and links, `trigger_commit`, `patch_commit` and
  `reference`.

A report can quote a proof of concept, as the upstream issue of many tasks
does, and a sanitizer log names the input that crashed the program. That is
part of the report, and the prompt shows it as it is. Write reports with that
in mind; see [Add a task](/guides/add-a-task).

The `test_patch` tool is not described in the prompt. Agents find it through
MCP, and what it runs depends on the
[difficulty level](/concepts/difficulty-levels).

## Example

The prompt for `gjson-196-bf4efcb`, shortened:

`````md
# Task

You are a software security engineer. Fix a confirmed vulnerability in gjson, a Go project, by modifying its source code.

## Objective
…
## Requirements
…
## Validation
…
## Vulnerability

### Report 1 of 2

```text
panic: runtime error: slice bounds out of range [1:0]
…
```

### Report 2 of 2

````text
```
package main
…
```
````

## Project

- Name: gjson
- Language: Go
- Source code: /src/gjson

## Build and test

### Build script
…
### Test script
…
`````

The full text is kept as a test snapshot,
`sdk/python/tests/snapshots/gjson-196-bf4efcb.prompt.md`; a change to the
prompt shows up there. Regenerate it with
`SSEBENCH_UPDATE_SNAPSHOTS=1 uv run pytest sdk/python/tests/test_prompt.py`.

## In your own agent

An agent in Python can send the same prompt:

```python
from sse.prompt import task_prompt

prompt = task_prompt()   # asks the daemon for the task's public metadata
```

`sse.prompt.build_prompt(metadata)` builds it from a `sse.metadata.Metadata`
without a daemon. An agent that writes its own prompt should give the model
every description field, as this one does, or its results are not comparable
with the bundled agents'.

## Next steps

- [Tasks and datasets](/concepts/tasks-and-datasets): the task config
- [Integrity model](/concepts/integrity): what is kept from the agent
- [Dialog protocol](/reference/dialog-protocol): where an agent records the
  prompt it sent
