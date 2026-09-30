import { afterAll, describe, expect, test } from "bun:test"
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { readGrade, resultsDir } from "./results"

const checkout = mkdtempSync(join(tmpdir(), "ssebench-results-"))
afterAll(() => rmSync(checkout, { recursive: true, force: true }))

const labels = {
  "ssebench.task-id": "demo-1",
  "ssebench.model": "test-model",
  "ssebench.agent": "dummy",
}

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
  const dir = join(checkout, "results", task, "test-model", "dummy", runId)
  return {
    dir,
    labels: {
      ...labels,
      "ssebench.task-id": task,
      "ssebench.run-id": runId,
      "ssebench.results": dir,
    },
  }
}

describe("resultsDir", () => {
  test("is the run directory that the container's label names", () => {
    const { dir, labels } = run("20260929-153012-a1b2c3")
    expect(resultsDir(labels, checkout)).toBe(dir)
  })

  test("derives the layout before run directories for a container without the label", () => {
    expect(resultsDir(labels, checkout)).toBe(
      join(checkout, "results", "demo-1", "test-model", "dummy")
    )
  })

  test("prefers the directory that a label names", () => {
    expect(
      resultsDir({ ...labels, "ssebench.results": "/data/run" }, checkout)
    ).toBe("/data/run")
  })

  test("refuses paths that leave the results tree", () => {
    for (const bad of ["../x", "a/../b", ".", "..", "-rf", "a b", ""]) {
      expect(resultsDir({ ...labels, "ssebench.task-id": bad }, checkout)).toBe(
        null
      )
      expect(resultsDir({ ...labels, "ssebench.agent": bad }, checkout)).toBe(
        null
      )
    }
    expect(
      resultsDir({ ...labels, "ssebench.results": "relative/dir" }, checkout)
    ).toBe(null)
    expect(
      resultsDir({ ...labels, "ssebench.results": "/data/../etc" }, checkout)
    ).toBe(null)
    expect(resultsDir({}, checkout)).toBe(null)
  })

  test("allows a model name with a provider prefix", () => {
    expect(
      resultsDir({ ...labels, "ssebench.model": "openai/gpt-5" }, checkout)
    ).toBe(join(checkout, "results", "demo-1", "openai", "gpt-5", "dummy"))
  })
})

describe("readGrade", () => {
  test("reads the grade that the run wrote", () => {
    const { dir, labels } = run("read-1")
    writeResult(dir, JSON.stringify(grade))

    expect(readGrade(labels, checkout)).toEqual({
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

    expect(readGrade(first.labels, checkout)?.patch_result).toEqual(
      failed as never
    )
    expect(readGrade(second.labels, checkout)?.patch_result).toEqual(
      grade.patch_result as never
    )
  })

  test("reads a container's grade from the layout before run directories", () => {
    writeResult(
      join(checkout, "results", "demo-5", "test-model", "dummy"),
      JSON.stringify(grade)
    )

    expect(
      readGrade({ ...labels, "ssebench.task-id": "demo-5" }, checkout)
        ?.available
    ).toBe(true)
  })

  test("is null for a run that has no result yet, beside runs that have one", () => {
    const done = run("done", "demo-6")
    const waiting = run("waiting", "demo-6")
    writeResult(done.dir, JSON.stringify(grade))
    mkdirSync(waiting.dir, { recursive: true })

    expect(readGrade(done.labels, checkout)).not.toBe(null)
    expect(readGrade(waiting.labels, checkout)).toBe(null)
  })

  test("is null while the evaluator has written nothing", () => {
    writeResult(join(checkout, "results", "demo-2", "test-model", "dummy"), "")
    expect(
      readGrade({ ...labels, "ssebench.task-id": "demo-2" }, checkout)
    ).toBe(null)
    expect(
      readGrade({ ...labels, "ssebench.task-id": "never-ran" }, checkout)
    ).toBe(null)
  })

  test("is null for a file that is not a grade", () => {
    const dir = join(checkout, "results", "demo-3", "test-model", "dummy")
    for (const content of ["{", "[]", '{"patch_result": 1}', '{"a": 1}']) {
      writeResult(dir, content)
      expect(
        readGrade({ ...labels, "ssebench.task-id": "demo-3" }, checkout)
      ).toBe(null)
    }
  })
})
