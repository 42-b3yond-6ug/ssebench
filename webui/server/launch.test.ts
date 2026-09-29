import { afterAll, describe, expect, test } from "bun:test"
import { rmSync } from "node:fs"
import { createFakes } from "./testing"

// launch.ts reads its paths at import time
const fakes = createFakes()
const savedEnv = { ...process.env }
Object.assign(process.env, fakes.env, {
  SSEBENCH_CATALOG_URL: "http://catalog.invalid",
})
const { buildLaunchArgs, validateLaunchConfig } = await import("./launch")
process.env = savedEnv

afterAll(() => {
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
      buildLaunchArgs({
        task: "demo-task-1",
        model: "test-model",
        agent: "dummy",
        mode: "sandbox",
        source: "local",
        timeout: 600,
        difficulty: 2,
      })
    ).toEqual([
      "run",
      "ssebench",
      "run",
      "--model=test-model",
      "--agent=dummy",
      "--task=demo-task-1",
      "--mode=sandbox",
      "--keep-container",
      `--local=${fakes.env.SSEBENCH_LOCAL_TASKS}`,
      "--timeout=600",
      "--difficulty=2",
    ])
  })
})
