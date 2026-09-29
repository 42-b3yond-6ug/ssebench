---
outline: deep
---

# MCP Server

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

1. **Build.** If the build fails, `test_patch` stops and reports the failure.
2. **PoCs.** Each proof of concept is run in turn; a PoC passes when it no longer triggers the bug. The first PoC that still triggers it ends this step, and the remaining checks still run. A task without PoCs passes this step.
3. **Intent tests**, the tests that came with the upstream fix. When they pass, the functional tests are counted as passed without being run.
4. **Functional tests**, the project's own regression tests. They run only when the intent tests are disabled or failed.

## Difficulty Levels

The server reads `SSE_DIFFICULTY` once, at startup. `ssebench run --difficulty` sets it; when it is unset the server uses level 2. Any value other than an integer from 0 to 4 stops the server from starting.

| Level | Name | Build | PoCs | Intent tests | Functional tests |
|-------|------|-------|------|--------------|------------------|
| 0 | `FULL_ASSISTANCE` | ✓ | ✓ | ✓ | ✓ |
| 1 | `NO_INTENT_TEST` | ✓ | ✓ | | ✓ |
| 2 | `NO_FUTURE_TEST` (default) | ✓ | | | ✓ |
| 3 | `BUILD_ONLY` | ✓ | | | |
| 4 | `NO_BUILD` | | | | |

At level 4, `test_patch` runs nothing and always reports success.

The difficulty level only limits what the agent can check while it works. Final grading by the evaluator always runs every check the task has.

## Return Value

`test_patch` returns a single text result.

When every enabled check passes:

```
Test succeeded: All checks passed. Your patch is valid. You may stop now.
```

When a check fails:

```
Test failed: <reason>

Full log:
<log>
```

The reason names the first failed check, in this order of precedence:

| Failed check | Reason |
|--------------|--------|
| Build | `The project failed to build. Please reassess the correctness of your patch.` |
| Functional tests | `One or more functionality test(s) failed. Please reassess your patch and make sure it fixes the vulnerability without compromising the program's functionality.` |
| PoCs | `The project failed to pass the proof-of-vulnerabilities test, only <passed> out of <total> proof-of-vulnerabilities didn't trigger a crash. Please reassess your patch and make sure it fixes the root cause of the vulnerability.` |
| Intent tests | `One or more intent test(s) failed. These tests validate behavior after the vulnerability fix. Please reassess your patch to ensure it correctly addresses the vulnerability and aligns with common patterns in the project.` |

The log is the standard output and standard error of the last check that failed, in the order the checks run.

### Long Logs

When the log is longer than 10,000 words, the server writes the full log to a file the agent can read, in `MCP_LOG_DIR` (default `/tmp/mcp/logs`), and returns only its tail: the last 100 lines or the last 10,000 words, whichever is shorter.

```
Test failed: <reason>

Truncated log:
<tail of the log>

Full log available at /tmp/mcp/logs/<uuid>.txt
```

If the file cannot be written, the last line reads `(Full log could not be saved due to an internal error)` instead.

### Internal Errors

If testing itself fails, for example because the daemon cannot be reached, `test_patch` returns:

```
An internal testing failure occurred. Your patch is not responsible for this failure.
```

## Next Steps

- [Architecture](/concepts/architecture) - How the MCP server fits into the task container
- [Environment Variables](/reference/environment) - Variables available inside the container
- [Dialog Protocol](/reference/dialog-protocol) - Integrate your agent with the Web UI
