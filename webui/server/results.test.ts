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

describe("resultsDir", () => {
  test("derives the directory from the run's labels", () => {
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
    writeResult(
      join(checkout, "results", "demo-1", "test-model", "dummy"),
      JSON.stringify(grade)
    )

    expect(readGrade(labels, checkout)).toEqual({
      available: true,
      patch_result: grade.patch_result,
      runtime_result: grade.runtime_result,
    } as never)
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
