import { afterAll, afterEach, describe, expect, test } from "bun:test"
import { existsSync, readFileSync, rmSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { createFakes, FULL_ID } from "./testing"

// launch.ts reads its paths at import time, and spawns `uv` with the
// environment of the moment, so the fakes stay in place until the end.
const fakes = createFakes()
const savedEnv = { ...process.env }
const events = join(fakes.dir, "uv-events.log")
const done = join(fakes.dir, "uv-done")
Object.assign(process.env, fakes.env, {
  SSEBENCH_CATALOG: "http://catalog.invalid",
  FAKE_UV_EVENTS: events,
  FAKE_UV_DONE: done,
})
const {
  buildLaunchArgs,
  clearLaunchEntry,
  clearAllLaunches,
  findRunContainer,
  getLaunchStatus,
  getPlugins,
  launchTask,
  validateLaunchConfig,
} = await import("./launch")

afterAll(() => {
  process.env = savedEnv
  rmSync(fakes.dir, { recursive: true, force: true })
})

const valid = {
  task: "demo-task-1",
  model: "test-model",
  agent: "dummy",
  mode: "sandbox",
  source: "local",
}

describe("validateLaunchConfig", () => {
  test("accepts a request for listed items", () => {
    const result = validateLaunchConfig({
      ...valid,
      timeout: 600,
      difficulty: 0,
    })
    expect(result).toEqual({
      ok: true,
      config: { ...valid, timeout: 600, difficulty: 0 } as never,
    })
  })

  test("accepts remote task IDs that are plain identifiers", () => {
    const result = validateLaunchConfig({
      ...valid,
      source: "remote",
      task: "generic-c-jq-jq_gh_3196",
    })
    expect(result.ok).toBe(true)
  })

  const payload = "x; touch /tmp/pwned"
  test.each([
    ["task", payload],
    ["task", "../../etc"],
    ["task", "--local=/"],
    ["task", "unknown-local-task"],
    ["model", payload],
    ["model", "--catalog=http://evil.example"],
    ["agent", payload],
    ["agent", "../agents"],
    ["mode", "sandbox --privileged"],
    ["source", "local; id"],
    ["timeout", "600; id"],
    ["timeout", -1],
    ["timeout", 1.5],
    ["difficulty", 5],
    ["difficulty", "2"],
  ])("rejects %s = %p", (field, value) => {
    expect(validateLaunchConfig({ ...valid, [field]: value }).ok).toBe(false)
  })

  test("the reference agent needs no model and ignores one", () => {
    const rest: Partial<typeof valid> = { ...valid }
    delete rest.model
    expect(validateLaunchConfig({ ...rest, agent: "reference" })).toEqual({
      ok: true,
      config: { ...rest, agent: "reference" } as never,
    })
    const withModel = validateLaunchConfig({
      ...valid,
      agent: "reference",
      model: "not-a-model",
    })
    expect(withModel.ok && withModel.config.model).toBeFalsy()
  })

  test("every other agent needs a listed model", () => {
    const rest: Partial<typeof valid> = { ...valid }
    delete rest.model
    expect(validateLaunchConfig(rest).ok).toBe(false)
  })

  test("accepts egress and known plugins for sandbox runs", () => {
    const result = validateLaunchConfig({
      ...valid,
      egress: "open",
      plugins: ["oracle", "oracle", "artifact"],
    })
    expect(result).toEqual({
      ok: true,
      config: {
        ...valid,
        egress: "open",
        plugins: ["oracle", "artifact"],
      } as never,
    })
  })

  test.each([
    ["egress", "everywhere"],
    ["egress", 1],
    ["plugins", "oracle"],
    ["plugins", ["nope"]],
    ["plugins", ["--flag"]],
    ["plugins", [1]],
  ])("rejects %s = %p", (field, value) => {
    expect(validateLaunchConfig({ ...valid, [field]: value }).ok).toBe(false)
  })

  test("rejects plugins in sidecar mode", () => {
    expect(
      validateLaunchConfig({ ...valid, mode: "sidecar", plugins: ["oracle"] })
        .ok
    ).toBe(false)
    expect(
      validateLaunchConfig({ ...valid, mode: "sidecar", plugins: [] }).ok
    ).toBe(true)
  })

  test("rejects remote payloads", () => {
    for (const task of [payload, "$(id)", "a/b", "-x"]) {
      expect(
        validateLaunchConfig({ ...valid, source: "remote", task }).ok
      ).toBe(false)
    }
  })

  test("rejects missing fields and non-objects", () => {
    expect(validateLaunchConfig({ ...valid, task: "" }).ok).toBe(false)
    expect(validateLaunchConfig(null).ok).toBe(false)
    expect(validateLaunchConfig("task").ok).toBe(false)
  })
})

describe("buildLaunchArgs", () => {
  test("binds every value to its option", () => {
    expect(
      buildLaunchArgs(
        {
          task: "demo-task-1",
          model: "test-model",
          agent: "dummy",
          mode: "sandbox",
          source: "local",
          timeout: 600,
          difficulty: 2,
          egress: "open",
          plugins: ["artifact", "oracle"],
        },
        "run-1"
      )
    ).toEqual([
      "run",
      "ssebench",
      "run",
      "--model=test-model",
      "--agent=dummy",
      "--task=demo-task-1",
      "--mode=sandbox",
      "--run-id=run-1",
      "--keep-container",
      `--local=${fakes.env.SSEBENCH_LOCAL_TASKS}`,
      "--timeout=600",
      "--difficulty=2",
      "--egress=open",
      "--plugin=artifact",
      "--plugin=oracle",
    ])
  })

  test("passes no model for the reference agent", () => {
    const args = buildLaunchArgs(
      { task: "t", agent: "reference", mode: "sandbox", source: "local" },
      "run-2"
    )
    expect(args.some((a) => a.startsWith("--model"))).toBe(false)
    expect(args).toContain("--run-id=run-2")
  })

  test("hands catalog tasks the catalog the server lists", () => {
    expect(
      buildLaunchArgs(
        {
          task: "gjson-196-bf4efcb",
          model: "test-model",
          agent: "dummy",
          mode: "sandbox",
          source: "remote",
        },
        "run-3"
      )
    ).toContain("--catalog=http://catalog.invalid")
  })
})

describe("getPlugins", () => {
  test("lists the plugins of plugins.yaml with their defaults", () => {
    expect(getPlugins()).toEqual([
      { name: "artifact", enabled: false, hook: "after-grading", llm: false },
      { name: "oracle", enabled: true, hook: "after-grading", llm: true },
    ])
  })
})

// A `uv` that keeps running, as `ssebench run --keep-container` does, until
// the test creates FAKE_UV_DONE. It records its arguments and how it ended.
const LONG_RUNNING_UV = `#!/bin/sh
for arg in "$@"; do printf '%s\\n' "$arg"; done >> "$FAKE_UV_LOG"
printf '%s\\n' '--' >> "$FAKE_UV_LOG"
trap 'echo terminated >> "$FAKE_UV_EVENTS"; exit 143' TERM
while [ ! -f "$FAKE_UV_DONE" ]; do sleep 0.05; done
echo finished >> "$FAKE_UV_EVENTS"
`

function psRow(
  id: string,
  labels: Record<string, string>,
  status = "Up 1 minute"
) {
  return JSON.stringify({
    ID: id,
    Names: `run-${id}`,
    Image: "agent-image",
    Status: status,
    Ports: "",
    Labels: Object.entries({ "ssebench.webui": "true", ...labels })
      .map(([k, v]) => `${k}=${v}`)
      .join(","),
    CreatedAt: "2026-01-01 00:00:00 +0000 UTC",
  })
}

const request = {
  task: "demo-task-1",
  model: "test-model",
  agent: "dummy",
  mode: "sandbox" as const,
  source: "local" as const,
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

describe("launch tracking", () => {
  const uv = join(fakes.binDir, "uv")

  afterEach(async () => {
    // Let every fake CLI end by itself before the next test reads the events
    writeFileSync(done, "")
    await sleep(200)
    clearAllLaunches()
    rmSync(done, { force: true })
    rmSync(events, { force: true })
    writeFileSync(fakes.psFile, "")
  })

  function useLongRunningUv() {
    writeFileSync(uv, LONG_RUNNING_UV, { mode: 0o755 })
    rmSync(done, { force: true })
    writeFileSync(events, "")
  }

  const eventLog = () =>
    readFileSync(events, "utf-8").split("\n").filter(Boolean)

  test("two launches of the same task each track their own container", async () => {
    useLongRunningUv()
    const first = await launchTask(request)
    const second = await launchTask(request)
    const label = (id: string) => ({
      "ssebench.task-id": request.task,
      "ssebench.run-id": id,
    })
    // Containers of the same task that are not these launches', one of them
    // newer than either, come first; the launches' own follow in reverse order.
    writeFileSync(
      fakes.psFile,
      [
        psRow("ffffffffffff", label("someone-elses-run")),
        psRow(
          "eeeeeeeeeeee",
          { "ssebench.task-id": request.task },
          "Exited (0) 1 hour ago"
        ),
        psRow("bbbbbbbbbbbb", label(second.launch_id)),
        psRow("aaaaaaaaaaaa", label(first.launch_id)),
      ].join("\n")
    )

    expect(await findRunContainer(first.launch_id)).toBe(true)
    expect(await findRunContainer(second.launch_id)).toBe(true)

    expect(getLaunchStatus(first.launch_id)).toMatchObject({
      status: "running",
      containerId: "aaaaaaaaaaaa",
    })
    expect(getLaunchStatus(second.launch_id)).toMatchObject({
      status: "running",
      containerId: "bbbbbbbbbbbb",
    })
  })

  test("a launch does not take a container of the same task that is not its own", async () => {
    useLongRunningUv()
    const launch = await launchTask(request)
    writeFileSync(
      fakes.psFile,
      psRow("ffffffffffff", {
        "ssebench.task-id": request.task,
        "ssebench.run-id": "someone-elses-run",
      })
    )

    expect(await findRunContainer(launch.launch_id)).toBe(false)
    expect(getLaunchStatus(launch.launch_id)?.status).toBe("launching")
  })

  test("the launch passes its ID to the CLI as the run ID", async () => {
    useLongRunningUv()
    const launch = await launchTask(request)
    await sleep(150)

    const argv = readFileSync(fakes.uvLog, "utf-8").split("\n")
    expect(argv).toContain(`--run-id=${launch.launch_id}`)
  })

  test("clearing a launch whose container exists leaves the CLI running to the end", async () => {
    useLongRunningUv()
    const launch = await launchTask(request)
    writeFileSync(
      fakes.psFile,
      psRow(FULL_ID.slice(0, 12), { "ssebench.run-id": launch.launch_id })
    )
    expect(await findRunContainer(launch.launch_id)).toBe(true)

    clearLaunchEntry(launch.launch_id)
    expect(getLaunchStatus(launch.launch_id)).toBeNull()
    await sleep(300)
    expect(eventLog()).toEqual([])

    writeFileSync(done, "")
    await sleep(300)
    expect(eventLog()).toEqual(["finished"])
  })

  test("clearing a launch that has no container yet stops the CLI", async () => {
    useLongRunningUv()
    const launch = await launchTask(request)
    await sleep(150)

    clearLaunchEntry(launch.launch_id)
    await sleep(300)

    expect(eventLog()).toEqual(["terminated"])
  })

  test("a CLI that ends without a container fails the launch", async () => {
    writeFileSync(uv, "#!/bin/sh\nexit 0\n", { mode: 0o755 })
    const launch = await launchTask(request)
    await sleep(300)

    expect(getLaunchStatus(launch.launch_id)).toMatchObject({
      status: "failed",
      error: "The run ended without starting a container",
    })
  })

  test("a CLI that ends after its container appeared still finds it", async () => {
    writeFileSync(
      uv,
      '#!/bin/sh\nwhile [ ! -f "$FAKE_UV_DONE" ]; do sleep 0.05; done\nexit 0\n',
      { mode: 0o755 }
    )
    rmSync(done, { force: true })
    const launch = await launchTask(request)
    writeFileSync(
      fakes.psFile,
      psRow("cccccccccccc", { "ssebench.run-id": launch.launch_id })
    )
    writeFileSync(done, "")
    await sleep(400)

    expect(getLaunchStatus(launch.launch_id)).toMatchObject({
      status: "running",
      containerId: "cccccccccccc",
    })
  })

  test("a failing CLI fails the launch with its exit code", async () => {
    writeFileSync(uv, "#!/bin/sh\nexit 3\n", { mode: 0o755 })
    const launch = await launchTask(request)
    await sleep(300)

    expect(getLaunchStatus(launch.launch_id)).toMatchObject({
      status: "failed",
      error: "Process exited with code 3",
    })
  })

  test("the recorded arguments were the fake's", () => {
    expect(existsSync(fakes.uvLog)).toBe(true)
  })
})
