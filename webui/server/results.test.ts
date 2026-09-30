import { afterAll, describe, expect, test } from "bun:test"
import {
  mkdirSync,
  mkdtempSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { readGrade, resultsDir } from "./results"

const root = mkdtempSync(join(tmpdir(), "ssebench-results-"))
afterAll(() => rmSync(root, { recursive: true, force: true }))

function writeResult(dir: string, content: string) {
  mkdirSync(dir, { recursive: true })
  writeFileSync(join(dir, "result.json"), content)
}

const grade = {
  patch_result: { build_success: true, pov_passed: 1, pov_total: 1 },
  runtime_result: {
    agent_duration: 3,
    agent_timeout: false,
    evaluator_timeout: false,
  },
  config: { agent: "dummy" },
}

/** The run directory of a run, and the labels its container carries */
function run(runId: string, task = "demo-1") {
  const dir = join(root, "results", task, "test-model", "dummy", runId)
  return {
    dir,
    labels: {
      "ssebench.task-id": task,
      "ssebench.run-id": runId,
      "ssebench.results": dir,
    },
  }
}

describe("resultsDir", () => {
  test("is the run directory that the container's label names", () => {
    const { dir, labels } = run("20260929-153012-a1b2c3")
    expect(resultsDir(labels)).toBe(dir)
  })

  test("is null without the label: a directory is never guessed from the task, model and agent", () => {
    expect(
      resultsDir({
        "ssebench.task-id": "demo-1",
        "ssebench.model": "test-model",
        "ssebench.agent": "dummy",
      })
    ).toBe(null)
    expect(resultsDir({})).toBe(null)
  })

  test("refuses paths that leave the results tree", () => {
    for (const bad of ["relative/dir", "/data/../etc", "..", ""]) {
      expect(resultsDir({ "ssebench.results": bad })).toBe(null)
    }
  })
})

describe("readGrade", () => {
  test("reads the grade that the run wrote", () => {
    const { dir, labels } = run("read-1")
    writeResult(dir, JSON.stringify(grade))

    expect(readGrade(labels)).toEqual({
      available: true,
      patch_result: grade.patch_result,
      runtime_result: grade.runtime_result,
    } as never)
  })

  test("gives each of two runs of one task, model and agent its own grade", () => {
    const first = run("trial-1", "demo-4")
    const second = run("trial-2", "demo-4")
    const failed = { ...grade.patch_result, pov_passed: 0 }
    writeResult(first.dir, JSON.stringify({ ...grade, patch_result: failed }))
    writeResult(second.dir, JSON.stringify(grade))

    expect(readGrade(first.labels)?.patch_result).toEqual(failed as never)
    expect(readGrade(second.labels)?.patch_result).toEqual(
      grade.patch_result as never
    )
  })

  test("is null for a run that has no result yet, beside runs that have one", () => {
    const done = run("done", "demo-6")
    const waiting = run("waiting", "demo-6")
    writeResult(done.dir, JSON.stringify(grade))
    mkdirSync(waiting.dir, { recursive: true })

    expect(readGrade(done.labels)).not.toBe(null)
    expect(readGrade(waiting.labels)).toBe(null)
  })

  test("is null while the evaluator has written nothing", () => {
    const { dir, labels } = run("empty", "demo-2")
    writeResult(dir, "")
    expect(readGrade(labels)).toBe(null)
    expect(readGrade(run("never-ran", "never").labels)).toBe(null)
  })

  test("is null for a file that is not a grade", () => {
    const { dir, labels } = run("garbage", "demo-3")
    for (const content of ["{", "[]", '{"patch_result": 1}', '{"a": 1}']) {
      writeResult(dir, content)
      expect(readGrade(labels)).toBe(null)
    }
  })

  test("does not follow a link in place of the grade", () => {
    const { dir, labels } = run("linked", "demo-7")
    mkdirSync(dir, { recursive: true })
    const elsewhere = join(root, "elsewhere.json")
    writeFileSync(elsewhere, JSON.stringify(grade))
    symlinkSync(elsewhere, join(dir, "result.json"))
    expect(readGrade(labels)).toBe(null)
  })
})
