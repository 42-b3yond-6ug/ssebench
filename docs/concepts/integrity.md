---
outline: deep
---

# Integrity model

A benchmark result means something only if the agent solved the task itself.
The agent under test is a capable program with a shell inside the task
container, and it may go looking for the answer, deliberately or not. This page
describes what SSEBench keeps from it, how, and where the protections stop.

It describes sandbox mode, the default. Sidecar mode is experimental and does
not provide all of these protections yet; see
[Sandbox and sidecar](/concepts/sandbox-and-sidecar).

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
|  /run/ssebench      0700  admin socket        /tmp/sse.sock   agent socket   |
|                                               :4263           daemon HTTP    |
|                                                                              |
+-------------------------------- network: <project>_agents (internal) --------+
                                          |
                                          v
                                   LiteLLM proxy only
```

### The agent runs unprivileged

The entrypoint runs as root. It starts the daemon, the MCP server and, at the
end, the evaluator as root, and the agent command as the user `model`
(uid 1000), in its own session. The tool image creates `model` and gives it
the project's source tree and its home directory; see
[Image layers](/concepts/image-layers#tool).

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

The agent learns what it needs through other channels: its prompt contains the
report files and the build and test scripts, and `test_patch` runs checks on
its behalf.

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
| `POST /tool/bencher?action=…` (`build`, `run_poc`, `function_test`, `intent_test`) | only the actions the difficulty level allows; the others return 403 | every action |
| `POST /tool/bash` | allowed; runs commands as `model` | allowed |
| `POST /prepare_grading` | 403 | allowed |
| `POST /admin/agent_exited` | 403 | allowed |
| `GET /reference/patch` | 403 until the agent phase ends | allowed |
| `GET /project`, `/capabilities`, `/diff`, `/files`, `/agent/dialog`, `/result`, `/final_diff`, `/version` | allowed | allowed |

`GET /project` returns the task's public view only: the project, the report
contents, the build and test scripts and the paths of the proofs of concept.
It leaves out the reference patch and the hidden tests.

### Difficulty is enforced by the daemon

The MCP server decides which checks `test_patch` runs, but the daemon enforces
the same limit itself: it reads `SSE_DIFFICULTY` at startup and answers 403 to
a withheld `bencher` action on its agent-facing listeners, so talking to the
daemon directly gains the agent nothing. A missing or invalid level counts as
the default, level 2. The evaluator grades through the admin socket, where
the gate does not apply, so grading always runs every check. See
[Difficulty levels](/concepts/difficulty-levels#where-the-level-is-enforced).

### The reference patch unlocks after the agent phase

The web UI shows the reference patch next to the agent's patch once a run is
over, so the daemon has to serve it at some point. It follows one rule:

- on the **admin socket**, `GET /reference/patch` works at any time;
- on the **agent-facing listeners**, it returns 403 until the agent phase has
  ended.

The phase ends when the entrypoint, after the agent process exits or is killed
at the timeout, sends `POST /admin/agent_exited` over the admin socket. Only
then does the evaluator start. From that moment the web UI can read the patch
from the host over port 4263. If the signal fails, the patch stays locked and
the entrypoint logs a warning.

Post-run tooling in Python reads it with the SDK:

```python
from sse.reference import get_reference_patch

patch = get_reference_patch()   # the unified diff, or "" if the task has none
```

The call goes to the daemon socket in `SSE_DAEMON_SOCKET`, so during the agent
phase, over the agent socket, it fails with a 403. The old name,
`sse.cheating.get_ground_truth`, still works for one release and warns that it
is deprecated.

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
  runs during the check, in the same container. The difficulty gate decides
  which checks the agent may ask for, not what that code does.
- **The model is outside the container.** The network policy stops the
  container from reaching the internet, not the model: requests to the proxy
  go to the provider, and a provider-hosted tool that a request turns on, such
  as web search, runs outside the container. A model may also know the
  upstream fix from its training data. SSEBench does not detect either.
- **Runs share a network.** Every run container of a Compose project joins the
  same `<project>_agents` network, so it can reach the other run containers
  there, including their daemon's HTTP port. A finished container kept with
  `--keep-container` serves its reference patch on that port. Do not keep
  finished containers of a task on the network while other runs of the same
  task are in progress, or give each experiment its own Compose project.
- **`--egress open` gives the agent the internet**, and with it the upstream
  repository and its fix. Use it only for tasks that need the network, and do
  not compare its results with restricted runs.
- **The agent's working files are not protected from the agent.** It owns its
  source tree and its home directory, and writes `dialog.jsonl` to the results
  directory. Treat `dialog.jsonl` and the other agent-written files as the
  agent's own account, not as evidence.

## Testing the protections

`tests/integrity/` holds a bypass suite. It starts a real sandbox container,
holds it in the agent phase, and runs `fake_agent.sh` as `model` to try the
known ways around the protections. At difficulty levels 0, 2 and 4 it checks
that:

- `GET /reference/patch` returns 403 on the agent socket and on HTTP;
- each `bencher` action is allowed or rejected with 403 exactly as the level
  says, on both listeners;
- the admin socket cannot be reached;
- the reference patch, the hidden tests, the proofs of concept and
  `/ssebench-repo` cannot be read;
- the source tree has at most one commit;
- the internet cannot be reached;
- the `bash` tool still works.

A separate test checks from the host that the reference patch is refused on
port 4263 during the agent phase and served after `POST /admin/agent_exited`.

The suite needs Docker and a sandbox tool image of `gjson-196-bf4efcb`, which
one run of that task builds:

```sh
make -C images/base-images generic-go
uv run ssebench run --local datasets/pilot --task gjson-196-bf4efcb --agent dummy --model claude-sonnet-4-6
uv run pytest tests/integrity -m integrity
```

`uv run python tests/integrity/test_bypass.py [LEVEL ...]` runs the same checks
as a script. `SSEBENCH_INTEGRITY_IMAGE` selects another tool image, and
`SSEBENCH_INTEGRITY_SOURCE` its source directory (default `/src/gjson`).
Without the image, the tests are skipped.

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
