---
outline: deep
---

# Difficulty levels

The difficulty level decides how much the agent can check its own work while
it runs. It limits the checks that the agent's `test_patch` tool runs, and
nothing else: the [grader](/concepts/grading) always runs every check the task
has, whatever the level.

Set it with `ssebench run --difficulty LEVEL`; the default is 2. The CLI
passes it to the container as `SSE_DIFFICULTY`, and the run summary records it
as `config.difficulty`.

## The levels

| Level | Name | `test_patch` runs | Withheld from the agent |
|---|---|---|---|
| 0 | `FULL_ASSISTANCE` | build, PoCs, intent tests, functional tests | nothing |
| 1 | `NO_INTENT_TEST` | build, PoCs, functional tests | intent tests |
| 2 | `NO_FUTURE_TEST` (default) | build, functional tests | PoCs, intent tests |
| 3 | `BUILD_ONLY` | build | every test |
| 4 | `NO_BUILD` | nothing | everything |

The checks are the ones described in [Tasks and datasets](/concepts/tasks-and-datasets#the-checks-a-task-defines):

- **build** runs the task's build script;
- **PoCs** run each proof of concept against the build;
- **functional tests** run the project's existing tests;
- **intent tests** apply the hidden tests from the upstream fix and run the
  tests again.

At the default level, `NO_FUTURE_TEST`, the agent can build the project and
run its existing test suite, but gets no result from the two checks that
decide whether the vulnerability is fixed: the proofs of concept and the tests
that came with the upstream fix. It has to find and fix the bug from the report
and the code. The lower levels hand it those signals, so it can iterate until
they pass; the higher levels take away even the build and the tests.

## What `test_patch` reports at each level

`test_patch` tests the source tree as it is, uncommitted changes included, in
this order:

1. **build**; if it fails, `test_patch` stops there;
2. **PoCs**, one at a time, stopping at the first that still triggers the bug;
3. **intent tests**;
4. **functional tests**, only when the intent tests are disabled or failed.
   When the intent tests pass, the functional tests count as passed without
   running.

Steps the level disables are skipped and count as passed. So at level 4,
`test_patch` runs nothing and always answers
`Test succeeded: All checks passed.`; at level 3, it reports success whenever
the project builds. When a check fails, the answer names it and includes the
check's output. The [MCP server reference](/reference/mcp-server#the-test-patch-tool)
lists the exact messages.

## Where the level is enforced

The level is enforced twice, so an agent that ignores `test_patch` and talks to
the daemon directly gets no more than `test_patch` would give it:

```
agent (user model)                                    evaluator (root)
   |                                                        |
   | test_patch                                             |
   v                                                        |
MCP server         runs only the checks the level enables   |
   |                                                        |
   v                                                        v
agent-facing socket /tmp/sse.sock    admin socket /run/ssebench/admin.sock
and HTTP :4263                       root only, never gated
   | gated: withheld bencher                                |
   | actions return 403                                     |
   v                                                        v
+----------------------------- ssebench-daemon ----------------------------+
|             build · run_poc · function_test · intent_test                |
+--------------------------------------------------------------------------+
```

- **The MCP server** (`runtime/mcp/config.py`) turns the level into the set of
  checks `test_patch` runs.
- **The daemon** reads `SSE_DIFFICULTY` once, at startup, and rejects the
  `bencher` actions that the level withholds with HTTP 403 on its agent-facing
  listeners, the Unix socket and the HTTP port:

  | Action | Allowed at levels |
  |---|---|
  | `build` | 0 to 3 |
  | `function_test` | 0 to 2 |
  | `run_poc` | 0 and 1 |
  | `intent_test` | 0 |

  The daemon's `bash` tool is not gated. It runs commands as the agent's own
  user, `model`, so it gives the agent nothing it could not do in its shell.

- **The grader** calls the same actions over the root-only admin socket, which
  the gate does not apply to, so final grading runs every check.

See the [integrity model](/concepts/integrity) for the two kinds of socket.

## Valid values

Use an integer from 0 to 4. `ssebench run` rejects any other `--difficulty`
before it builds or starts anything, and so does the web UI's launch form.
Inside the container, the daemon and the MCP server read `SSE_DIFFICULTY` on
their own: unset, it means level 2; set to anything but an integer from 0 to
4, including an empty string, each refuses to start. The run then fails
without grading, and its result has `status` `error`; a run never goes ahead
at a level other than the one asked for.

## Comparing results

Final grading is the same at every level, so the grades of runs at different
levels measure the same thing: whether the patch builds, stops the proofs of
concept and passes the tests. What changes is how much feedback the agent had
while it worked. Compare agents and models at the same level, and group results
by `config.difficulty` when you mix levels; a gap between level 0 and level 2
shows how much an agent relies on being told that its fix works.

## Next steps

- [Grading pipeline](/concepts/grading): the checks the grader runs
- [MCP server](/reference/mcp-server): the `test_patch` tool
- [Results format](/concepts/results): where the level is recorded
