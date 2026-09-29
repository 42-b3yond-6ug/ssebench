---
outline: deep
---

# Integrity model

A benchmark result means something only if the agent solved the task itself.
The agent under test is a capable program with a shell inside the task
container, and it may go looking for the answer, deliberately or not. This page
describes what SSEBench keeps from it, how, and where the protections stop.

It describes sandbox mode, the default. Sidecar mode keeps the same
protections across its two containers; see
[Sandbox and sidecar](/concepts/sandbox-and-sidecar#security-properties) for
what differs.

## What must stay hidden

While the agent works, it must not be able to:

- read the **reference patch**, the upstream fix (`files.patch`);
- read the **hidden tests** (`files.future_test`) or the **proofs of concept**;
- recover the **upstream fix commit** from the project's history;
- get the result of a **check its [difficulty level](/concepts/difficulty-levels)
  withholds**, such as the PoCs at the default level;
- look the fix up on the **internet**.

And nothing the agent does may change **how it is graded**, other than the
patch it leaves behind. [SECURITY.md](https://github.com/42-b3yond-6ug/ssebench/blob/main/SECURITY.md)
treats a way around any of these as a vulnerability.

## The protections

```
+-- task container (sandbox mode) ---------------------------------------------+
|                                                                              |
|  root                                         user model (uid 1000)          |
|  ----                                         ---------------------          |
|  entrypoint, daemon, MCP server, evaluator    the agent                      |
|                                                                              |
|  /ssebench          0700  task files          /src/<project>  source tree,   |
|  /ssebench-repo     0700  original source                     one commit     |
|  /var/lib/ssebench  0700  the grade, logs     /tmp/sse-archive  dialog, logs |
|  /run/ssebench      0700  admin socket        /tmp/sse.sock   agent socket   |
|                                               :4263           daemon HTTP    |
|                                                                              |
|                          user sse-runner (a third uid, no groups)            |
|                          ---------------------------------------             |
|                          build, PoC and test scripts, in a scratch copy      |
|                                                                              |
+-------------------------------- network: <project>_agents (internal) --------+
                                          |
                                          v
                                   LiteLLM proxy only
```

### The agent runs unprivileged

The entrypoint runs as root. It starts the daemon and the MCP server as root,
and the agent command as the user `model` (uid 1000), in its own session. The
tool layer creates `model` fresh, with no supplementary groups, so it does not
inherit a base image's uid-1000 user and its `sudo` or `adm` membership; see
[Image layers](/concepts/image-layers#tool).

### Task scripts run as a third, unprivileged user

A check builds and tests the agent's source tree, so it runs code the agent
wrote (a `Makefile` rule, a `go test` file, a `build.rs`). None of that runs
as root or as the agent. The daemon runs every task script — build, PoC,
function and intent tests — as **`sse-runner`**, a dedicated uid with no
groups, neither `model` nor root, in a scratch copy of the project under
`/var/lib/ssebench-runner`:

- root prepares the copy with only what the check needs, and adds hidden
  material (the intent-test diff) into it at grading time;
- `sse-runner` cannot read `/ssebench`, `/ssebench-repo` or the run's results,
  and cannot reach the admin socket (its `SSE_ADMIN_SOCKET` is cleared);
- the scratch copies live in a directory `model` cannot enter (`0710`,
  root-owned, `sse-runner`'s group), so the agent cannot read hidden material
  staged there;
- after the process tree exits, root kills every remaining `sse-runner`
  process (code that daemonises escapes the process group, so the whole
  user's processes go) before it collects the output;
- grading starts a fresh `sse-runner` session, so nothing a check left behind
  during `test_patch` — a build cache, a file in a support directory, a
  process — takes part in grading.

A PoC still runs in the folder the grading build produced: the sanitizer-crash
semantics (a non-zero exit means the vulnerability still triggers) are
unchanged.

### Task files are root-only

The case image puts the task's files in `/ssebench`, and the tool layer makes
that directory readable by root only (mode 0700):

| Path | Contents |
|---|---|
| `/ssebench/config.yaml` | The task config |
| `/ssebench/diffs/` | The reference patch and the hidden tests |
| `/ssebench/pocs/` | The proofs of concept |
| `/ssebench/reports/` | The report files |
| `/ssebench/scripts/` | The build, run and test scripts |
| `/ssebench-repo` | The project as the case image built it, used for grading (also 0700) |

The agent learns what it needs through other channels: its
[prompt](/concepts/prompt) contains the task's description, the report files
and the build and test scripts, and `test_patch` runs checks on its behalf. So
the runner can execute them, the build and test scripts and any support
directory they use in place (a Rust harness at `/ssebench/harness`, say) are
readable and executable by `sse-runner`'s group only; the reference patch, the
hidden tests, the proofs of concept and the config stay root-only.

The one exception is the `reference` agent, which applies the known fix to
check a task rather than a model. For that agent only, `ssebench run` copies
the reference patch out of the case image and mounts it read-only at
`/reference/patch.diff`; the daemon still serves it only on the admin socket.
The run is labelled with `config.reference_run` and never counts as a model's
score; see [Reference runs](/reference/cli#reference-runs).

### Grading outputs are root-only

Two directories hold what a run produces, and they are kept apart:

| Directory | Env | Owner | Holds |
|---|---|---|---|
| results | `SSE_RESULTS`, `/var/lib/ssebench/results` | written by root; `0700` root parent | `result.json` (the grade), `final.patch`, `commits.log`, the logs |
| archive | `SSE_ARCHIVE`, `/tmp/sse-archive` | `model` | `dialog.jsonl` and whatever the agent side writes |

The CLI mounts the run directory at the results path and its `archive/`
subdirectory at the archive path; the result the CLI trusts is
`result.json` there, written only by root. The parent of the results
directory is `0700` root, so neither `model` nor `sse-runner` can reach it,
whoever owns the run directory on the host. The evaluator writes the grade
with an atomic replace into that directory, and the daemon writes `final.patch`
and its logs there too, so a symlink the agent plants in its own archive
cannot redirect a root write. The agent gets its own archive directory back
when the agent phase ends, so a run can be cleared for the next one.

### The project's history is replaced

Upstream history would give the fix away, for example through `git log` on a
checkout that contains later commits. When the tool image is built, every
`.git` directory in the source tree, submodules included, is deleted, and the
tree is committed again as one commit:

```console
$ git log --oneline
276db8f buggy commit
```

The original checkout, with whatever history the case image had, is only in
the root-only `/ssebench-repo`.

### The daemon has two kinds of listener

The daemon, `ssebench-daemon`, is what builds and tests the project, so it
decides what the agent can get from it. It serves the same API on three
listeners, of two kinds:

| Listener | Address | Who can reach it | Kind |
|---|---|---|---|
| Agent socket | Unix socket `SSE_DAEMON_SOCKET`, default `/tmp/sse.sock`, mode 0666 | everyone in the container | agent-facing |
| HTTP | port 4263 on all interfaces | the container, and the web UI from the host | agent-facing |
| Admin socket | Unix socket `SSE_ADMIN_SOCKET`, default `/run/ssebench/admin.sock`, mode 0600 in a 0700 directory | root: the entrypoint and the evaluator | privileged |

On the agent-facing listeners:

| Endpoint | Agent-facing | Admin socket |
|---|---|---|
| `POST /tool/bencher?action=…` (`build`, `run_poc`, `function_test`, `intent_test`) | during the agent phase, only the actions the difficulty level allows; a `grading` argument or any call after the phase returns 403 | every action |
| `POST /tool/bash` | during the agent phase; runs commands as `model` | allowed |
| `POST /prepare_grading` | 403 | allowed |
| `POST /admin/agent_exited` | 403 | allowed |
| `GET /reference/patch` | 403 | allowed |
| `GET /project`, `/capabilities`, `/diff`, `/files`, `/agent/dialog`, `/result`, `/final_diff`, `/version` | allowed | allowed |

The git-backed endpoints (`/diff`, `/files`) and the patch capture run git on
the agent's source tree against a private copy of its base commit, as the
tree's owner and with the repository's own configuration ignored, so a
configuration the agent plants (a hook, a filter, `fsmonitor`) runs nothing as
root; see [Capturing the patch](/concepts/grading#_1-capturing-the-patch).

`GET /project` returns the task's public view only: the project, the report
contents, the build and test scripts and the paths of the proofs of concept.
It leaves out the reference patch and the hidden tests.

### Difficulty is enforced by the daemon

The MCP server decides which checks `test_patch` runs, but the daemon enforces
the same limit itself: it reads `SSE_DIFFICULTY` at startup and answers 403 to
a withheld `bencher` action on its agent-facing listeners, so talking to the
daemon directly gains the agent nothing. A missing level counts as the
default, level 2, and an invalid one stops the daemon from starting. The
evaluator grades through the admin socket, where the gate does not apply, so
grading always runs every check. See
[Difficulty levels](/concepts/difficulty-levels#where-the-level-is-enforced).

### The reference patch is on the admin socket only

`GET /reference/patch` is served only on the admin socket, which only root in
the daemon's container can reach. The agent-facing listeners refuse it at all
times, before and after the agent phase, because the HTTP listener on port 4263
is reachable from the other run containers on the network, and from a container
kept after the run.

The agent phase still ends: when the agent process exits or is killed at the
timeout, the entrypoint sends `POST /admin/agent_exited` over the admin socket.
From then on the daemon refuses every tool on the agent-facing listeners and
kills the agent user's processes, so nothing the agent left running takes part
in grading. It does not open the reference patch to those listeners.

Post-run consumers get the patch elsewhere:

- **The web UI** reads it on the host, from `reference.patch` in the run's
  results directory (the CLI copies it there once the run is over) or from the
  task folder in the local dataset; it knows both.
- **Root tooling inside the container** (the evaluator, a plugin) reads it with
  the SDK, which goes to the admin socket:

  ```python
  from sse.reference import get_reference_patch

  patch = get_reference_patch()   # the unified diff, or "" if the task has none
  ```

  The call needs `SSE_ADMIN_SOCKET`, so it works only as root; the agent, over
  the agent socket, cannot reach it. The old name,
  `sse.cheating.get_ground_truth`, still works for one release and warns that
  it is deprecated.

### No internet by default

By default the run container joins the Compose project's internal network,
`<project>_agents`, on which it can reach the LiteLLM proxy and nothing
outside the host: no internet, and no DNS for outside names.
`ssebench run --egress open` puts it on a normal bridge instead. The run
summary records the policy as `config.egress`. See
[Integrity and egress](/deployment/integrity-and-egress).

## Limits

These protections make the answer hard to reach from inside the run. They do
not make the container a hardened sandbox, and some channels are outside their
reach:

- **The container is the boundary.** The agent shares the container, and its
  kernel, with processes that run as root and can read the answer. The
  protections rely on ordinary Unix permissions and Docker's default
  isolation. Run only agents you are prepared to run in Docker on that host.
- **The checks run the project's own code.** A check that `test_patch` runs
  builds and tests the agent's modified source tree, so code the agent writes
  runs during the check. That code runs as `sse-runner`, which cannot read the
  hidden material or the grade and cannot reach the admin socket, in a scratch
  copy `model` cannot enter; but it shares the container's kernel with the
  root processes, so it is contained by ordinary Unix permissions, not
  sandboxed. The difficulty gate decides which checks the agent may ask for,
  not what that code does once a check runs it.
- **The model is outside the container.** The network policy stops the
  container from reaching the internet, not the model: requests to the proxy
  go to the provider, and a provider-hosted tool that a request turns on, such
  as web search, runs outside the container. A model may also know the
  upstream fix from its training data. SSEBench does not detect either.
- **Runs share a network.** Every run container of a Compose project joins the
  same `<project>_agents` network, so it can reach the other run containers
  there, including their daemon's HTTP port on 4263. That port no longer serves
  the reference patch, or any grading route, so a concurrent or kept run cannot
  read another run's answer through it. It still exposes that run's public view
  and its live diff; give each experiment its own Compose project if even that
  should be private.
- **`--egress open` gives the agent the internet**, and with it the upstream
  repository and its fix. Use it only for tasks that need the network, and do
  not compare its results with restricted runs.
- **The agent's working files are not protected from the agent.** It owns its
  source tree and its home directory, and writes `dialog.jsonl` to the results
  directory. Treat `dialog.jsonl` and the other agent-written files as the
  agent's own account, not as evidence.

## Testing the protections

`tests/integrity/` holds a bypass suite. It starts a real run, in each mode,
holds it in the agent phase, and runs `fake_agent.sh` as `model` in the agent's
container to try the known ways around the protections. At difficulty levels
0, 2 and 4 it checks that:

- `GET /reference/patch` returns 403 on the agent socket and on HTTP;
- each `bencher` action is allowed or rejected with 403 exactly as the level
  says, on both listeners;
- the admin socket cannot be reached, and neither daemon socket can be
  moved;
- the reference patch, the hidden tests, the proofs of concept,
  `/ssebench-repo` and `/reference/patch.diff` cannot be read, and the task
  files not through the daemon's `bash` tool either, which in sidecar mode
  runs in the task container;
- the source tree has at most one commit;
- the internet cannot be reached, directly or through the `bash` tool;
- the `bash` tool still works.

A separate test checks from the host that the reference patch is refused on
port 4263 during the agent phase and served after `POST /admin/agent_exited`.
The unit tests in `bench/tests/test_reference_run.py` build the container
commands of every agent in `agents/`, in both modes, and check that only the
`reference` agent gets the reference patch mount.

The suite needs Docker and the images of `gjson-196-bf4efcb`, which one run of
that task in each mode builds:

```sh
make -C images/base-images generic-go
uv run ssebench run --local datasets/pilot --task gjson-196-bf4efcb --agent dummy --model claude-sonnet-4-6
uv run ssebench run --local datasets/pilot --task gjson-196-bf4efcb --agent dummy --model claude-sonnet-4-6 --mode sidecar
uv run pytest tests/integrity -m integrity
```

`uv run python tests/integrity/test_bypass.py [--mode sidecar] [LEVEL ...]`
runs the same checks as a script. `SSEBENCH_INTEGRITY_IMAGE` selects another
sandbox tool image, `SSEBENCH_INTEGRITY_SIDECAR_ENV_IMAGE` and
`SSEBENCH_INTEGRITY_SIDECAR_AGENT_IMAGE` other sidecar images, and
`SSEBENCH_INTEGRITY_SOURCE` their source directory (default `/src/gjson`).
The tests of a mode whose images are missing are skipped.

A change that touches any of these protections must keep the suite passing,
and a newly found bypass should come with a check that tries it.

## Reporting a bypass

Report a way around these protections **privately**, as described in the
[security policy](https://github.com/42-b3yond-6ug/ssebench/blob/main/SECURITY.md):
through GitHub's private vulnerability reporting, or by email. Do not open a
public issue or pull request; a public bypass can be used to inflate results
before it is fixed. Include the task, agent, mode and difficulty level, and
what the agent gains.

## Next steps

- [Integrity and egress](/deployment/integrity-and-egress): the network policy
  and deployment settings
- [Difficulty levels](/concepts/difficulty-levels)
- [Grading pipeline](/concepts/grading)
- [Add an agent](/guides/add-an-agent#what-an-agent-must-not-do): what an
  agent's author must respect
