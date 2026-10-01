import {
  afterAll,
  beforeAll,
  beforeEach,
  describe,
  expect,
  test,
} from "bun:test"
import {
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import type { StaticRunData } from "../src/types/container"
import { forgetPastRuns } from "./pastRuns"
import { readReferencePatch } from "./reference"
import { forgetRuns, refreshRuns } from "./runner"
import { runData } from "./runData"
import { exportStaticData, staticHealth } from "./staticExport"
import { createFakes, pastJson, setState, type Fakes } from "./testing"

const PATCH = "diff --git a/f b/f\n--- a/f\n+++ b/f\n@@ -0,0 +1 @@\n+x\n"
const NOW = new Date("2026-01-02T03:04:05Z")

let fakes: Fakes
let root: string
let out: string
const savedEnv: Record<string, string | undefined> = {}

function runDir(name: string): string {
  const dir = join(root, name)
  mkdirSync(join(dir, "archive"), { recursive: true })
  writeFileSync(join(dir, "final.patch"), PATCH)
  writeFileSync(
    join(dir, "archive", "dialog.jsonl"),
    '{"seq":0,"type":"init"}\nnot json\n{"seq":1,"type":"message"}\n'
  )
  writeFileSync(
    join(dir, "result.json"),
    JSON.stringify({ patch_result: { status: "passed" }, runtime_result: {} })
  )
  writeFileSync(
    join(dir, "summary.json"),
    JSON.stringify({ task: { id: "demo-task-1", project: "demo" } })
  )
  writeFileSync(join(dir, "reference.patch"), "reference\n")
  writeFileSync(join(dir, "post-review.txt"), "Looks fine\n")
  writeFileSync(join(dir, "agent.log"), "line one\nline two\n")
  return dir
}

beforeAll(() => {
  fakes = createFakes()
  for (const [key, value] of Object.entries(fakes.env)) {
    savedEnv[key] = process.env[key]
    process.env[key] = value
  }
  root = mkdtempSync(join(tmpdir(), "static-export-"))
  out = join(root, "out")
})

afterAll(() => {
  for (const [key, value] of Object.entries(savedEnv)) {
    if (value === undefined) delete process.env[key]
    else process.env[key] = value
  }
  rmSync(fakes.dir, { recursive: true, force: true })
  rmSync(root, { recursive: true, force: true })
})

beforeEach(() => {
  refreshRuns()
  forgetRuns("one")
  forgetPastRuns()
})

const readJson = (path: string) =>
  JSON.parse(readFileSync(join(out, path), "utf-8"))

describe("exportStaticData", () => {
  test("writes the files a hosted server would answer with", async () => {
    const one = runDir("one")
    const two = runDir("two")
    setState(fakes, {
      past: [
        pastJson("one", one, { started_at: "2026-01-02T00:00:00Z" }),
        pastJson("two", two, { started_at: "2026-01-01T00:00:00Z" }),
        // the same ID again, older: the newest wins, as in the server
        pastJson("one", two, { started_at: "2025-01-01T00:00:00Z" }),
        // not a run ID a URL can name
        pastJson("latest", two),
      ],
    })

    const summary = await exportStaticData(out, {
      tasksDir: join(root, "no-tasks"),
      now: NOW,
    })
    expect(summary).toEqual({ runs: 2 })
    expect(readdirSync(join(out, "data")).sort()).toEqual([
      "health.json",
      "runs",
      "runs.json",
    ])
    expect(readdirSync(join(out, "data", "runs")).sort()).toEqual([
      "one.json",
      "two.json",
    ])

    expect(readJson("data/health.json")).toEqual(staticHealth(NOW))
    expect(readJson("data/health.json")).toMatchObject({
      hosted: true,
      terminal: false,
      assistant: false,
    })

    const list = readJson("data/runs.json")
    expect(list.containers.map((c: { id: string }) => c.id)).toEqual([
      "one",
      "two",
    ])
    expect(list.containers[0]).toMatchObject({
      status: "exited",
      source: "results",
    })

    // The same answers the server gives for the same run directory
    setState(fakes, { past: [pastJson("one", one)] })
    const data: StaticRunData = readJson("data/runs/one.json")
    expect(data.diff).toBe(PATCH)
    expect({ diff: data.diff }).toEqual(
      (await runData("one", "/diff")).data as never
    )
    expect({ files: data.files }).toEqual(
      (await runData("one", "/files")).data as never
    )
    expect({ entries: data.dialog }).toEqual(
      (await runData("one", "/agent/dialog")).data as never
    )
    expect(data.result).toEqual((await runData("one", "/result")).data as never)
    expect(data.project).toEqual(
      (await runData("one", "/project")).data as never
    )
    expect(data.container.id).toBe("one")
    expect(data.referencePatch).toBe(
      readReferencePatch({ "ssebench.results": one }, join(root, "none")) ?? ""
    )
    expect(data.referencePatch).toBe("reference\n")
    expect(data.review).toEqual({ available: true, text: "Looks fine\n" })
    expect(data.logs).toBe("==> agent.log <==\nline one\nline two\n")
  })

  test("does not follow links in a run directory", async () => {
    const secret = join(root, "secret.txt")
    writeFileSync(secret, "secret")
    const dir = runDir("linked")
    rmSync(join(dir, "post-review.txt"))
    symlinkSync(secret, join(dir, "post-review.txt"))
    rmSync(join(dir, "agent.log"))
    symlinkSync(secret, join(dir, "agent.log"))
    setState(fakes, { past: [pastJson("linked", dir)] })

    await exportStaticData(out, { tasksDir: join(root, "none"), now: NOW })
    const data: StaticRunData = readJson("data/runs/linked.json")
    expect(data.review).toEqual({ available: false })
    expect(data.logs).toBe("")
    expect(JSON.stringify(data)).not.toContain("secret")
  })

  test("a run that left no patch or grade exports empty views", async () => {
    const dir = join(root, "bare")
    mkdirSync(dir)
    setState(fakes, { past: [pastJson("bare", dir)] })
    await exportStaticData(out, { tasksDir: join(root, "none"), now: NOW })
    expect(readJson("data/runs/bare.json")).toMatchObject({
      project: null,
      diff: null,
      files: [],
      dialog: [],
      result: null,
      referencePatch: "",
      review: { available: false },
      logs: "",
    })
  })
})
