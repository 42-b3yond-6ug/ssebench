import {
  afterAll,
  beforeAll,
  beforeEach,
  describe,
  expect,
  test,
} from "bun:test"
import { rmSync, writeFileSync } from "node:fs"
import { forgetPastRuns } from "./pastRuns"
import { refreshRuns } from "./runner"
import { getContainer, listContainers, resolveRun } from "./runs"
import {
  createFakes,
  injectionPayloads,
  invocations,
  pastJson,
  runJson,
  setState,
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
  refreshRuns()
  forgetPastRuns()
})

describe("listContainers", () => {
  test("lists the backend's runs, then the finished runs it no longer has", async () => {
    setState(fakes, {
      runs: [
        runJson("live", { state: "running" }),
        runJson("kept", { state: "exited" }),
      ],
      past: [
        pastJson("kept", "/r/kept"),
        pastJson("gone", "/r/gone", { status: "passed" }),
      ],
    })

    const { containers, runnerError } = await listContainers()

    expect(runnerError).toBeUndefined()
    expect(containers.map((c) => [c.id, c.status, c.source])).toEqual([
      ["live", "running", "container"],
      ["kept", "exited", "container"],
      ["gone", "exited", "results"],
    ])
  })

  test("still lists the finished runs when the backend cannot be listed", async () => {
    setState(fakes, { past: [pastJson("gone", "/r/gone")] })
    const original = process.env.SSEBENCH_CLI
    const script = `${fakes.dir}/half.sh`
    writeFileSync(
      script,
      `#!/bin/sh\ncase "$2" in results) exec ${original} "$@" ;; *) echo 'docker is down' >&2; exit 1 ;; esac\n`,
      { mode: 0o755 }
    )
    process.env.SSEBENCH_CLI = script
    try {
      const { containers, runnerError } = await listContainers()
      expect(containers.map((c) => c.id)).toEqual(["gone"])
      expect(runnerError).toContain("docker is down")
    } finally {
      process.env.SSEBENCH_CLI = original
    }
  })

  test("finds one run by its ID", async () => {
    setState(fakes, { runs: [runJson("live")], past: [pastJson("gone", "/r")] })
    expect((await getContainer("gone"))?.source).toBe("results")
    expect((await getContainer("live"))?.source).toBe("container")
    expect(await getContainer("nope")).toBeNull()
  })
})

describe("resolveRun", () => {
  test("a run on the backend has the labels of its container and the directory they name", async () => {
    setState(fakes, {
      runs: [
        runJson("live", {
          results_dir: "/r/live",
          labels: { "ssebench.results": "/r/live", "ssebench.run-id": "live" },
        }),
      ],
    })
    expect(await resolveRun("live")).toEqual({
      id: "live",
      source: "container",
      status: "running",
      labels: { "ssebench.results": "/r/live", "ssebench.run-id": "live" },
      resultsDir: "/r/live",
    })
  })

  test("a finished run without a container is read-only history with labels made from its listing", async () => {
    setState(fakes, { past: [pastJson("gone", "/r/gone")] })
    expect(await resolveRun("gone")).toMatchObject({
      id: "gone",
      source: "results",
      status: "exited",
      resultsDir: "/r/gone",
      labels: {
        "ssebench.results": "/r/gone",
        "ssebench.task-id": "demo-task-1",
      },
    })
  })

  test("a run on the backend that has no directory label gets the one results/ lists", async () => {
    setState(fakes, {
      runs: [runJson("both", { state: "exited" })],
      past: [pastJson("both", "/r/both")],
    })
    expect((await resolveRun("both"))?.resultsDir).toBe("/r/both")
  })

  test("an unknown run, and an ID that is not one, resolve to nothing", async () => {
    setState(fakes, { runs: [runJson("live")] })
    expect(await resolveRun("nope")).toBeNull()
    for (const payload of injectionPayloads(fakes.marker)) {
      expect(await resolveRun(payload)).toBeNull()
    }
    expect(await invocations(fakes.callsLog)).toEqual([
      ["runs", "list", "--json"],
      ["runs", "results", "--json"],
    ])
  })
})
