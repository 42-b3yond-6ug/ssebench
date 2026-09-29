---
outline: deep
---

# Watching a run

The run view shows one run's container: what the agent said and did, the diff it
left, the grade, the container's logs, and a shell in the container. The dialog,
the diff, the grade and the reference patch come from the container's own
[daemon](/reference/daemon-api), which the web UI reaches at the container's IP
address on port 4263. The web UI therefore has to run on a host that can route to
container addresses, as a Linux Docker host does.

![The run view of a reference run: the agent dialog, the diff, and the logs](/images/webui/run-view.png)

## Getting to a run

The sidebar has one tab per attached container. It shows the task ID, the model
and the agent, and whether the container is running.

- When the page loads, the web UI attaches **every running container** that
  carries the label `ssebench.webui`. Containers that exited are not attached.
- **Attach to Container** lists all such containers in four tabs: **Running**,
  **Exited**, **All**, and **Recent** for the last ten you attached in this
  browser. Filter by task, model, agent, image or container name, select a row
  and click **Attach**.
- A container you launch from the wizard is attached for you; see
  [Launching runs](/webui/launching-runs).
- A run started with `ssebench run --keep-container` appears in the list too,
  whoever started it.

The list is every container with that label on the Docker daemon, whoever
started it and whichever Compose project it belongs to. On a shared daemon you
see other people's runs, and can stop them.

### Runs from the command line

`--keep-container` keeps the container running after grading, so the web UI can
show it. The CLI then waits until the container stops, and writes the run
summary at that point:

```sh
uv run ssebench run --local datasets/pilot --task gjson-196-bf4efcb \
    --agent reference --keep-container
```

When you stop the container, the CLI may log `Agent container stopped with a
non-zero exit ... exit status 137` before it writes the summary as usual. That is
the exit status of a container that was stopped, and does not mean the run
failed.

## Layout

The bar at the top of a run shows the task ID and its language, the source
directory inside the container, the model and the agent. **More Details** opens
the task's description, crash reports and PoC files, and the SDK version is on
the right. The three buttons next to it hide and show the left, center and
bottom areas.

| Area | Contents |
|---|---|
| Left | [Agent dialog](#agent-dialog) |
| Center | [Changes](#changes-and-files), [Files](#changes-and-files), [AI](#ai-assistant), [Terminal](#terminal), [Evaluation Result](#evaluation-result) |
| Bottom | [Terminal](#terminal) and [Logs](#logs) |

The dividers between the areas can be dragged. **Settings** in the sidebar moves
the tab bars and changes the terminal colors.

While the container starts, the panels read `Initializing SDK...`. The web UI
waits up to 25 minutes for the daemon to answer, then polls it every 1 to 10
seconds, faster while things change, through one WebSocket per run.

## Agent dialog

The left area replays `dialog.jsonl`, the file that the agent writes in
`$SSE_ARCHIVE` (see [Dialog protocol](/reference/dialog-protocol)):

| Entry | Shows |
|---|---|
| Session Started | The agent, the model and the task |
| Task Prompt | The prompt the agent got, shortened to 300 characters with **Show more** |
| Assistant | The agent's message as Markdown, with its token counts |
| Thinking | The reasoning, collapsed until you click it |
| Tool call | The tool's name, arguments and result, with a status: running, success or error. Results are cut at 1000 characters |
| Session Completed, Failed or Timed Out | The number of turns, the duration and the total tokens |

The footer reads `Waiting for agent...`, `Live` while entries arrive, and
`Session complete` once the agent has finished or a grade exists, with the
number of the latest entry. The download button saves the entries as
`dialog.jsonl`, and the refresh button reconnects.

An agent that writes no dialog leaves the panel at `No dialog yet`. The `dummy`
agent writes none.

## Changes and files

**Changes** shows the agent's diff: every change in the source tree since the
vulnerable commit, with the files collapsible, the added and removed lines
counted, and syntax highlighting. **Parsed** and **Raw** switch between the
cards and the plain diff, which you can download as `patch.diff`. **Files** lists
the changed files with `A`, `M`, `D` or `R` and their line counts.

### The reference patch

Once the agent's phase is over, the daemon serves the task's reference patch, and
the header gains three buttons:

| Button | Shows |
|---|---|
| **Agent** | The agent's diff |
| **Truth** | The reference patch, under a purple banner that names it "ground truth" |
| **Split** | Both, side by side |

Next to them, **Similarity** is the share of changed lines that the two diffs
have in common, after normalizing whitespace, in green from 80%, yellow from 40%
and red below. It compares text and is not a grade; the grade is the
[Evaluation Result](#evaluation-result). The reference patch is fetched once,
when the run opens. If you opened it while the agent was still working, the
buttons stay missing until you reload the page.

## Evaluation Result

![The Evaluation Result tab of a reference run](/images/webui/evaluation.png)

The tab reads `No evaluation yet` until the evaluator has written the grade. The
card then shows the checks of the [grading pipeline](/concepts/grading):

| Check | Shows |
|---|---|
| **Build** | Whether the project builds with the patch |
| **Func** | Whether the project's own tests pass |
| **Security** | How many of the task's proofs of concept the patch defeats, as passed over total |
| **Intent** | Whether the tests of the upstream fix pass |

Below the checks it shows how long the agent ran, a `TIMEOUT` mark if it hit its
time limit, and the evaluator's error message, with the error log behind
**Show log**. `N/A` marks a check that did not run for the task.

On a [reference run](/reference/cli#reference-runs) the card carries a note that
the grade checks the task, not a model.

In sidecar mode this tab stays empty. The grade is written where the daemon
cannot read it, so read `result.json` in `results/` instead.

## Logs

The **Logs** tab streams `docker logs -f` of the container from its start: the
entrypoint, the daemon, the MCP server, the agent and the evaluator. It follows
the end unless you scroll up; **Bottom** jumps back.

## Terminal

The terminal is a shell in the container, started with `docker exec -it` as the
image's default user, which is `root`. Use it to look at the project, the
results in `$SSE_ARCHIVE` (`/tmp/sse-archive`) and the task files under
`/ssebench`. The toolbar changes the font size, searches, clears and restarts
the shell.

- It needs a helper that `just webui` does not build. From `webui/`, run
  `bun run build:pty`, which needs Go; the [container image](/webui/#in-a-container)
  includes it. Without the helper, the terminal prints `Terminal unavailable:
  pty-proxy is not built`, while the rest of the run view works.
- The container has to be running.
- `SSEBENCH_WEBUI_TERMINAL=0` turns the terminal off and hides its tabs; see
  [Security model](/webui/security#terminal).
- A terminal process is cleaned up after five minutes without activity; the
  `PTY_*` variables in [Environment variables](/reference/environment#web-ui)
  change that.

## AI assistant

The **AI** tab runs [OpenCode](https://opencode.ai/) in the container as a
debugging assistant. It comes with prompts for comparing the agent's fix with the
reference patch, for reviewing the changes, and for looking for problems. The
assistant works with your own Anthropic API key, which you enter under
**Settings**, and it can run commands in the container. Read
[the key and the assistant](/webui/security#provider-api-key-and-the-assistant)
before you use it.

The assistant calls Anthropic from inside the container. A container on the
default `restricted` network cannot reach the internet, so the assistant cannot
answer there: the message you send stays without a reply, and the browser shows
no error. Use the assistant on a run started with `--egress open`.

## Containers

Hover over the tab of a container and click its cross to open **Detach
Container?**:

| Choice | Does |
|---|---|
| **Detach** | Closes the tab. The container keeps running, and you can attach again |
| **Detach + Stop** | Closes the tab, kills the container and removes it. Only offered for a running container |
| **Cancel** | Does nothing |

The web UI only touches containers with the label `ssebench.webui`. A container
that stops by itself, or by `docker stop`, stays on the list as **Exited**. The
web UI cannot remove it; use `docker rm <container>`.

A kept container serves its daemon API, including the reference patch, for as
long as it runs. Stop kept containers when you are done, and do not keep
finished containers of a task while other runs of that task are in progress; see
[Integrity and egress](/deployment/integrity-and-egress#what-the-restricted-policy-does-not-cover).

## Next steps

- [Launching runs](/webui/launching-runs)
- [Dialog protocol](/reference/dialog-protocol): write a `dialog.jsonl` for your
  own agent
- [Results format](/concepts/results): what the CLI records for a run
- [Security model](/webui/security)
