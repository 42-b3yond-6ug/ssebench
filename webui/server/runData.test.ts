import {
  afterAll,
  beforeAll,
  beforeEach,
  describe,
  expect,
  test,
} from "bun:test"
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import type { Server } from "bun"
import { forgetPastRuns } from "./pastRuns"
import { forgetRuns, refreshRuns } from "./runner"
import { runData, usesDaemon } from "./runData"
import { createFakes, pastJson, runJson, setState, type Fakes } from "./testing"

let fakes: Fakes
let daemon: Server<unknown>
let dir: string
const PATCH = "diff --git a/f b/f\n--- a/f\n+++ b/f\n@@ -0,0 +1 @@\n+x\n"
const savedEnv: Record<string, string | undefined> = {}

beforeAll(() => {
  fakes = createFakes()
  for (const [key, value] of Object.entries(fakes.env)) {
    savedEnv[key] = process.env[key]
    process.env[key] = value
  }
  daemon = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    fetch(req) {
      const path = new URL(req.url).pathname
      return Response.json({ from: "daemon", path })
    },
  })
  dir = mkdtempSync(join(tmpdir(), "run-data-"))
  mkdirSync(join(dir, "archive"))
  writeFileSync(join(dir, "final.patch"), PATCH)
  writeFileSync(
    join(dir, "archive", "dialog.jsonl"),
    '{"seq":0,"type":"init"}\n{"seq":1,"type":"message"}\n'
  )
  writeFileSync(
    join(dir, "result.json"),
    JSON.stringify({ patch_result: { status: "passed" }, runtime_result: {} })
  )
  writeFileSync(
    join(dir, "summary.json"),
    JSON.stringify({ task: { id: "demo-task-1", project: "demo" } })
  )
})

afterAll(() => {
  daemon.stop(true)
  for (const [key, value] of Object.entries(savedEnv)) {
    if (value === undefined) delete process.env[key]
    else process.env[key] = value
  }
  rmSync(fakes.dir, { recursive: true, force: true })
  rmSync(dir, { recursive: true, force: true })
})

beforeEach(() => {
  refreshRuns()
  forgetRuns("live")
  forgetPastRuns()
})

test("usesDaemon: only a run with a container that is not over", () => {
  const run = (source: "container" | "results", status: string) =>
    ({ id: "r", source, status, labels: {}, resultsDir: null }) as never
  expect(usesDaemon(run("container", "running"))).toBe(true)
  expect(usesDaemon(run("container", "unknown"))).toBe(true)
  expect(usesDaemon(run("container", "exited"))).toBe(false)
  expect(usesDaemon(run("container", "created"))).toBe(false)
  expect(usesDaemon(run("results", "exited"))).toBe(false)
})

describe("a running run", () => {
  test("is asked through the URL the backend gives", async () => {
    setState(fakes, {
      runs: [runJson("live")],
      endpoints: { "4263": `http://127.0.0.1:${daemon.port}` },
      past: [pastJson("live", dir)],
    })
    expect(await runData("live", "/diff")).toEqual({
      data: { from: "daemon", path: "/diff" },
      status: 200,
    })
  })

  test("is 503 while the daemon cannot be reached", async () => {
    setState(fakes, { runs: [runJson("live")] })
    expect((await runData("live", "/diff")).status).toBe(503)
  })
})

describe("a run that is over", () => {
  const over = () =>
    setState(fakes, {
      runs: [runJson("live", { state: "exited" })],
      past: [pastJson("live", dir)],
    })

  test("answers from its run directory, as the daemon would", async () => {
    over()
    expect(await runData("live", "/diff")).toEqual({
      data: { diff: PATCH },
      status: 200,
    })
    expect((await runData("live", "/files")).data).toEqual({
      files: [{ path: "f", status: "modified", additions: 1, deletions: 0 }],
    })
    expect((await runData("live", "/agent/dialog")).data).toEqual({
      entries: [
        { seq: 0, type: "init" },
        { seq: 1, type: "message" },
      ],
    })
    expect((await runData("live", "/agent/dialog?since=0")).data).toEqual({
      entries: [{ seq: 1, type: "message" }],
    })
    expect((await runData("live", "/project")).data).toMatchObject({
      id: "demo-task-1",
      project: "demo",
    })
    expect((await runData("live", "/result")).data).toMatchObject({
      available: true,
    })
  })

  test("has no daemon to ask, so a request the files cannot answer is 404", async () => {
    over()
    expect((await runData("live", "/version")).status).toBe(404)
  })

  test("a finished run whose container is gone answers the same way", async () => {
    setState(fakes, { past: [pastJson("gone", dir)] })
    expect((await runData("gone", "/diff")).status).toBe(200)
  })

  test("a run that wrote no patch has nothing to show for the diff, but an empty dialog", async () => {
    const empty = mkdtempSync(join(tmpdir(), "run-data-empty-"))
    setState(fakes, { past: [pastJson("empty", empty)] })
    expect((await runData("empty", "/diff")).status).toBe(404)
    expect((await runData("empty", "/agent/dialog")).data).toEqual({
      entries: [],
    })
    expect((await runData("empty", "/result")).data).toEqual({
      available: false,
    })
    rmSync(empty, { recursive: true })
  })
})

test("an unknown run is 404", async () => {
  setState(fakes, {})
  expect((await runData("nope", "/diff")).status).toBe(404)
})
