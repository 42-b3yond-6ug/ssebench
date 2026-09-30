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

/** A CLI that runs `script` instead of the fake runner */
function fakeCli(script: string) {
  const cli = join(fakes.dir, "cli.sh")
  writeFileSync(cli, `#!/bin/sh\n${script}\n`, { mode: 0o755 })
  process.env.SSEBENCH_CLI = cli
}

describe("getDoctorReport", () => {
  test("returns the report that the CLI prints", async () => {
    fakeCli(`echo '${JSON.stringify(report)}'`)
    expect(await getDoctorReport()).toEqual({
      available: true,
      report,
    } as never)
  })

  test("still returns it when a required check made the CLI exit 1", async () => {
    fakeCli(`echo '${JSON.stringify(report)}'; exit 1`)
    expect((await getDoctorReport()).available).toBe(true)
  })

  test("says so when there is no report", async () => {
    fakeCli("echo 'not json'; exit 2")
    const result = await getDoctorReport()
    expect(result.available).toBe(false)
  })

  test("reuses a recent report", async () => {
    fakeCli(`echo '${JSON.stringify(report)}'`)
    const first = await getDoctorReport()
    fakeCli("exit 2")
    expect(await getDoctorReport()).toBe(first)
  })
})
