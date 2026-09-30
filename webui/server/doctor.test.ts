import { afterAll, beforeEach, describe, expect, test } from "bun:test"
import { rmSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { getDoctorReport, resetDoctorCache } from "./doctor"
import { createFakes } from "./testing"

const fakes = createFakes()
const savedEnv = { ...process.env }
Object.assign(process.env, fakes.env)
afterAll(() => {
  process.env = savedEnv
  rmSync(fakes.dir, { recursive: true, force: true })
})
beforeEach(resetDoctorCache)

const report = {
  checks: [{ name: "Docker", status: "ok", detail: "daemon 29", fix: "" }],
  models: { claude: { keys: ["ANTHROPIC_API_KEY"], missing: [] } },
}

function fakeUv(script: string) {
  writeFileSync(join(fakes.binDir, "uv"), `#!/bin/sh\n${script}\n`, {
    mode: 0o755,
  })
}

describe("getDoctorReport", () => {
  test("returns the report that the CLI prints", async () => {
    fakeUv(`echo '${JSON.stringify(report)}'`)
    expect(await getDoctorReport()).toEqual({
      available: true,
      report,
    } as never)
  })

  test("still returns it when a required check made the CLI exit 1", async () => {
    fakeUv(`echo '${JSON.stringify(report)}'; exit 1`)
    expect((await getDoctorReport()).available).toBe(true)
  })

  test("says so when there is no report", async () => {
    fakeUv("echo 'not json'; exit 2")
    const result = await getDoctorReport()
    expect(result.available).toBe(false)
  })

  test("reuses a recent report", async () => {
    fakeUv(`echo '${JSON.stringify(report)}'`)
    const first = await getDoctorReport()
    fakeUv("exit 2")
    expect(await getDoctorReport()).toBe(first)
  })
})
