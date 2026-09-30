import {
  afterAll,
  beforeAll,
  beforeEach,
  describe,
  expect,
  test,
} from "bun:test"
import { existsSync, rmSync, writeFileSync } from "node:fs"
import {
  checkRunnerAccess,
  containerEnv,
  endpointOf,
  execCommand,
  forgetRuns,
  getSDKUrl,
  isRunId,
  listRuns,
  refreshRuns,
  removeRun,
  runnerCommand,
  stopRun,
  toContainer,
  type RunnerRun,
} from "./runner"
import {
  createFakes,
  injectionPayloads,
  invocations,
  readState,
  RUN_ID,
  runJson,
  setState,
  SHORT_ID,
  type Fakes,
} from "./testing"

let fakes: Fakes
const savedEnv: Record<string, string | undefined> = {}

beforeAll(() => {
  fakes = createFakes()
  for (const [key, value] of Object.entries(fakes.env)) {
    savedEnv[key] = process.env[key]
    process.env[key] = value
  }
})

afterAll(() => {
  for (const [key, value] of Object.entries(savedEnv)) {
    if (value === undefined) delete process.env[key]
    else process.env[key] = value
  }
  rmSync(fakes.dir, { recursive: true, force: true })
})

beforeEach(() => {
  writeFileSync(fakes.callsLog, "")
  setState(fakes, { runs: [runJson(RUN_ID)] })
  refreshRuns()
  forgetRuns(RUN_ID)
})

describe("isRunId", () => {
  test("accepts the IDs the CLI makes and accepts", () => {
    for (const id of [
      RUN_ID,
      SHORT_ID,
      "trial-1",
      "a",
      "a.b_c-d",
      "x".repeat(64),
    ])
      expect(isRunId(id)).toBe(true)
    // the UI's own launch IDs are UUIDs
    expect(isRunId(crypto.randomUUID())).toBe(true)
  })

  test("rejects what the CLI rejects, and what could be read as an option or a path", () => {
    for (const value of [
      "",
      "x".repeat(65),
      "-rf",
      ".hidden",
      "_x",
      "latest",
      "LATEST",
      "a/b",
      "a b",
      undefined,
      42,
      ...injectionPayloads("/tmp/pwned"),
    ]) {
      expect(isRunId(value)).toBe(false)
    }
  })
})

describe("runnerCommand", () => {
  test("is uv run ssebench unless SSEBENCH_CLI says otherwise", () => {
    expect(runnerCommand({})).toEqual(["uv", "run", "ssebench"])
    expect(runnerCommand({ SSEBENCH_CLI: "  ssebench  " })).toEqual([
      "ssebench",
    ])
    expect(
      runnerCommand({ SSEBENCH_CLI: "uv run --project /opt/ssebench ssebench" })
    ).toEqual(["uv", "run", "--project", "/opt/ssebench", "ssebench"])
  })
})

describe("operations on runs", () => {
  test("injection payloads never reach the CLI or a shell", async () => {
    for (const payload of injectionPayloads(fakes.marker)) {
      expect(await stopRun(payload)).toBe("refused")
      expect(await removeRun(payload)).toBe("refused")
      expect(await endpointOf(payload, 4263)).toBeNull()
      expect(await getSDKUrl(payload)).toBeNull()
      expect(await containerEnv(payload, ["SSE_BASE_URL"])).toBeNull()
    }
    expect(await invocations(fakes.callsLog)).toEqual([])
    expect(existsSync(fakes.marker)).toBe(false)
  })

  test("stop asks the CLI for the run by its ID", async () => {
    expect(await stopRun(RUN_ID)).toBe("ok")
    expect(await invocations(fakes.callsLog)).toEqual([
      ["runs", "stop", RUN_ID],
    ])
    expect(readState(fakes).runs[0].state).toBe("exited")
  })

  test("remove asks the CLI, and the run is gone afterwards", async () => {
    expect(await removeRun(RUN_ID)).toBe("ok")
    expect(await invocations(fakes.callsLog)).toEqual([
      ["runs", "remove", RUN_ID],
    ])
    expect(readState(fakes).runs).toEqual([])
  })

  test("stop and remove succeed again for a run that is gone", async () => {
    setState(fakes, {})
    expect(await stopRun(RUN_ID)).toBe("ok")
    expect(await removeRun(RUN_ID)).toBe("ok")
  })

  test("an ID that several runs share is refused, not guessed", async () => {
    const original = process.env.SSEBENCH_CLI
    const script = `${fakes.dir}/ambiguous.sh`
    writeFileSync(script, "#!/bin/sh\necho 'two runs' >&2\nexit 4\n", {
      mode: 0o755,
    })
    process.env.SSEBENCH_CLI = script
    try {
      expect(await stopRun(RUN_ID)).toBe("ambiguous")
      expect(await removeRun(RUN_ID)).toBe("ambiguous")
    } finally {
      process.env.SSEBENCH_CLI = original
    }
  })

  test("a CLI that fails makes the operation fail", async () => {
    const original = process.env.SSEBENCH_CLI
    const script = `${fakes.dir}/failing.sh`
    writeFileSync(script, "#!/bin/sh\necho boom >&2\nexit 1\n", { mode: 0o755 })
    process.env.SSEBENCH_CLI = script
    try {
      expect(await stopRun(RUN_ID)).toBe("failed")
    } finally {
      process.env.SSEBENCH_CLI = original
    }
  })
})

describe("listing", () => {
  test("callers within a moment share one command", async () => {
    await Promise.all([listRuns(), listRuns(), listRuns()])
    await listRuns()
    expect(await invocations(fakes.callsLog)).toEqual([
      ["runs", "list", "--json"],
    ])
    refreshRuns()
    await listRuns()
    expect((await invocations(fakes.callsLog)).length).toBe(2)
  })

  test("reports the backend and whether it runs commands", async () => {
    expect(await checkRunnerAccess()).toEqual({
      ok: true,
      backend: "fake",
      supportsExec: true,
    })
    setState(fakes, { backend: "cluster", supports_exec: false })
    refreshRuns()
    expect(await checkRunnerAccess()).toEqual({
      ok: true,
      backend: "cluster",
      supportsExec: false,
    })
  })

  test("reports a CLI that cannot list, and does not remember the failure", async () => {
    const original = process.env.SSEBENCH_CLI
    process.env.SSEBENCH_CLI = "/nonexistent/ssebench"
    try {
      const result = await checkRunnerAccess()
      expect(result.ok).toBe(false)
    } finally {
      process.env.SSEBENCH_CLI = original
    }
    refreshRuns()
    expect((await checkRunnerAccess()).ok).toBe(true)
  })

  test("a run becomes the UI's container with the run ID as its ID", () => {
    const run = runJson("r1", {
      state: "exited",
      reference_run: true,
      model: "none",
    }) as unknown as RunnerRun
    expect(toContainer(run)).toMatchObject({
      id: "r1",
      runId: "r1",
      status: "exited",
      referenceRun: true,
      model: "none",
      taskId: "demo-task-1",
      source: "container",
    })
    expect(toContainer({ ...run, state: "unknown" }).status).toBe("unknown")
    expect(toContainer({ ...run, task: null }).taskId).toBe("unknown")
  })
})

describe("reaching a run", () => {
  test("the URL of a port comes from the backend, and is remembered", async () => {
    setState(fakes, {
      runs: [runJson(RUN_ID)],
      endpoints: { "4263": "http://10.1.2.3:4263" },
    })
    expect(await getSDKUrl(RUN_ID)).toBe("http://10.1.2.3:4263")
    expect(await getSDKUrl(RUN_ID)).toBe("http://10.1.2.3:4263")
    expect(await invocations(fakes.callsLog)).toEqual([
      ["runs", "endpoint", "--json", RUN_ID, "4263"],
    ])
  })

  test("a run that is not running has no URL", async () => {
    setState(fakes, {
      runs: [runJson(RUN_ID, { state: "exited" })],
      endpoints: { "4263": "http://10.1.2.3:4263" },
    })
    expect(await getSDKUrl(RUN_ID)).toBeNull()
  })

  test("stopping a run forgets its URLs", async () => {
    setState(fakes, {
      runs: [runJson(RUN_ID)],
      endpoints: { "4263": "http://10.1.2.3:4263" },
    })
    await getSDKUrl(RUN_ID)
    await stopRun(RUN_ID)
    expect(await getSDKUrl(RUN_ID)).toBeNull()
  })
})

describe("commands in a run", () => {
  test("the command reaches the CLI as separate words, after the run ID and --", () => {
    const payload = "'; touch /tmp/pwned; echo '"
    expect(
      execCommand(RUN_ID, ["opencode", "run", payload], {
        user: "model",
        workdir: "/src",
        tty: true,
        stdin: true,
        envNames: ["OPENCODE_CONFIG_CONTENT"],
      })
    ).toEqual([
      ...runnerCommand(),
      "runs",
      "exec",
      "--user",
      "model",
      "--workdir",
      "/src",
      "--tty",
      "--stdin",
      "--env",
      "OPENCODE_CONFIG_CONTENT",
      RUN_ID,
      "--",
      "opencode",
      "run",
      payload,
    ])
  })

  test("variables of a container are read by a command in it", async () => {
    setState(fakes, {
      runs: [runJson(RUN_ID)],
      env: { [RUN_ID]: { SSE_BASE_URL: "http://litellm:4000" } },
    })
    expect(
      await containerEnv(RUN_ID, ["SSE_BASE_URL", "SSE_MODEL_NAME"])
    ).toEqual({ SSE_BASE_URL: "http://litellm:4000", SSE_MODEL_NAME: "" })
  })

  test("only variable names can be asked for", async () => {
    expect(await containerEnv(RUN_ID, ["$(id)"])).toBeNull()
    expect(await containerEnv(RUN_ID, ["a b"])).toBeNull()
    expect(await invocations(fakes.callsLog)).toEqual([])
  })

  test("a backend that cannot run commands gives no variables", async () => {
    setState(fakes, { runs: [runJson(RUN_ID)], supports_exec: false })
    expect(await containerEnv(RUN_ID, ["SSE_BASE_URL"])).toBeNull()
  })
})
