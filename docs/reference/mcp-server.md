---
outline: deep
---

# MCP server

Every task container runs an MCP (Model Context Protocol) server that gives the agent a single tool, `test_patch`, to check its work while it runs. The server is built on [FastMCP](https://gofastmcp.com/); its source is in `runtime/mcp/`.

## Connecting

The container entrypoint starts the server before the agent and waits until it responds, for up to `SSE_MCP_TIMEOUT` seconds (default 300). In sidecar mode it runs in the agent container.

| Setting | Value |
|---------|-------|
| Transport | Streamable HTTP |
| URL | `http://localhost:3000/mcp` |
| Tools | `test_patch` |

The bundled agents register the server under the name `ssebench`. Claude Code, for example, is configured with:

```bash
claude mcp add ssebench http://localhost:3000/mcp --transport http --scope user
```

Any MCP client that supports the Streamable HTTP transport can connect the same way. A call runs a full build and test cycle, so allow a generous tool timeout; the bundled Codex agent allows an hour.

## The `test_patch` Tool

`test_patch` takes **no arguments**. It tests the current state of the task's source tree, including every uncommitted change the agent has made, by asking the SDK daemon to build the project and run the task's checks.

The checks run in this order. Which of them run depends on the [difficulty level](#difficulty-levels).

1. **Build.** If the build fails, `test_patch` stops and reports the failure; the checks after it are reported as not run.
2. **PoCs.** Each proof of concept is run in turn; a PoC passes when it no longer triggers the bug. The first PoC that still triggers it ends this step, and the remaining checks still run. A task without PoCs passes this step.
3. **Intent tests**, the tests that came with the upstream fix. When they pass, the functional tests are counted as passed without being run.
4. **Functional tests**, the project's own regression tests. They run only when the intent tests are disabled or failed.

## Difficulty Levels

The server reads `SSE_DIFFICULTY` once, at startup. `ssebench run --difficulty` sets it; when it is unset the server uses level 2. Any value other than an integer from 0 to 4 stops the server from starting, as it stops the daemon.

| Level | Name | Build | PoCs | Intent tests | Functional tests |
|-------|------|-------|------|--------------|------------------|
| 0 | `FULL_ASSISTANCE` | ✓ | ✓ | ✓ | ✓ |
| 1 | `NO_INTENT_TEST` | ✓ | ✓ | | ✓ |
| 2 | `NO_FUTURE_TEST` (default) | ✓ | | | ✓ |
| 3 | `BUILD_ONLY` | ✓ | | | |
| 4 | `NO_BUILD` | | | | |

A check the level disables is not run and is not reported as passed: the result lists it as not available. At level 4, `test_patch` runs nothing and reports that no checks ran.

The difficulty level only limits what the agent can check while it works. Final grading by the evaluator always runs every check the task has. The daemon enforces the same limits on its own, so an agent that calls it directly gets no more than `test_patch` gives; see [Difficulty levels](/concepts/difficulty-levels).

## Return Value

`test_patch` returns a single text result. It lists the checks that ran and how each ended, and it names the checks that the difficulty level makes unavailable. It never calls the patch valid and never tells the agent to stop: a result reports on the checks behind it and on nothing else, and at the default level those checks cannot show that the vulnerability is fixed.

The result has these parts, separated by a blank line:

1. **The headline**, one of:
   - `test_patch result: every check passed.` when the level enables every check and all passed;
   - `test_patch result: every check that ran passed.` when the level withholds some checks and every enabled check passed;
   - `test_patch result: no checks ran.` at level 4;
   - `test_patch result: FAILED. <reason>` when a check failed.
2. **`Checks:`**, one line per check the level enables, in the order they run: `- <check>: passed`, `- <check>: FAILED` or `- <check>: not run (the build failed)`, with the detail below in parentheses where there is one. Omitted at level 4.
3. **The availability note**, present when the level withholds any check: `Not available at difficulty level <n> (<NAME>): <checks>. Nothing is reported about them.` A passing result that has no PoC result adds `Without the PoCs, this result does not show whether the vulnerability is fixed.`, and at level 4 `test_patch has nothing to run at this level, so this result says nothing about your patch.`
4. **The log** of the failed check, when a check failed (see below).

The checks are named `build`, `PoCs`, `intent tests` and `functional tests`. Details in parentheses:

| Check | Detail |
|-------|--------|
| PoCs | `<passed> of <total>` when all passed; `the task has none` for a task without PoCs; `passed <n> of <total>; stopped at the first that still triggers the bug` when one failed |
| Functional tests | `covered by the intent tests` when the intent tests passed, so the functional tests were not run separately |
| Any check | `the build failed` when it was not run because the build failed |

### Examples

At level 2 (the default), the PoCs and the intent tests are withheld. A tree that still contains the vulnerability builds and passes the project's own tests, so the result is:

```
test_patch result: every check that ran passed.

Checks:
- build: passed
- functional tests: passed

Not available at difficulty level 2 (NO_FUTURE_TEST): PoCs, intent tests. Nothing is reported about them. Without the PoCs, this result does not show whether the vulnerability is fixed.
```

At level 0, nothing is withheld:

```
test_patch result: every check passed.

Checks:
- build: passed
- PoCs: passed (2 of 2)
- intent tests: passed
- functional tests: passed (covered by the intent tests)
```

At level 1, the intent tests are withheld:

```
test_patch result: every check that ran passed.

Checks:
- build: passed
- PoCs: passed (2 of 2)
- functional tests: passed

Not available at difficulty level 1 (NO_INTENT_TEST): intent tests. Nothing is reported about them.
```

At level 3, only the build runs:

```
test_patch result: every check that ran passed.

Checks:
- build: passed

Not available at difficulty level 3 (BUILD_ONLY): PoCs, intent tests, functional tests. Nothing is reported about them. Without the PoCs, this result does not show whether the vulnerability is fixed.
```

At level 4, nothing runs:

```
test_patch result: no checks ran.

Not available at difficulty level 4 (NO_BUILD): build, PoCs, intent tests, functional tests. Nothing is reported about them. test_patch has nothing to run at this level, so this result says nothing about your patch.
```

When a check fails, for example the build at level 2:

```
test_patch result: FAILED. The project failed to build. Please reassess the correctness of your patch.

Checks:
- build: FAILED
- functional tests: not run (the build failed)

Not available at difficulty level 2 (NO_FUTURE_TEST): PoCs, intent tests. Nothing is reported about them.

Full log (build):
<log>
```

### Failure reasons

The headline of a failed result carries the reason for the first failed check, in this order of precedence:

| Failed check | Reason |
|--------------|--------|
| Build | `The project failed to build. Please reassess the correctness of your patch.` |
| Functional tests | `One or more functionality test(s) failed. Please reassess your patch and make sure it fixes the vulnerability without compromising the program's functionality.` |
| PoCs | `At least one proof-of-concept (PoC) still triggers the vulnerability. Please reassess your patch and make sure it fixes the root cause of the vulnerability.` |
| Intent tests | `One or more intent test(s) failed. These tests validate behavior after the vulnerability fix. Please reassess your patch to ensure it correctly addresses the vulnerability and aligns with common patterns in the project.` |

The log is the standard output and standard error of the check named in the reason. Its heading names the check: `Full log (<check>):`.

### Long Logs

When the log is longer than 10,000 words, the server writes the full log to a file the agent can read, in `MCP_LOG_DIR` (default `/tmp/mcp/logs`), and returns only its tail: the last 100 lines or the last 10,000 words, whichever is shorter.

```
test_patch result: FAILED. <reason>

Checks:
...

Truncated log (<check>):
<tail of the log>

Full log available at /tmp/mcp/logs/<uuid>.txt
```

If the file cannot be written, the last line reads `(Full log could not be saved due to an internal error)` instead.

### Internal Errors

If testing itself fails, for example because the daemon cannot be reached, `test_patch` returns:

```
An internal testing failure occurred. Your patch is not responsible for this failure.
```

## Next steps

- [Architecture](/concepts/architecture): how the MCP server fits into the task container
- [Grading pipeline](/concepts/grading): how final grading differs from `test_patch`
- [Environment variables](/reference/environment): variables available inside the container
- [Dialog protocol](/reference/dialog-protocol): show your agent's session in the web UI
- [Add an agent](/guides/add-an-agent#the-test-patch-tool): call `test_patch` from
  your own agent
