import { describe, expect, test } from "bun:test"
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { RESULTS_LABEL, readReferencePatch } from "./reference"

function dataset(): string {
  const dir = mkdtempSync(join(tmpdir(), "reference-"))
  const sse = join(dir, "demo-1", "sse")
  mkdirSync(join(sse, "diffs"), { recursive: true })
  writeFileSync(
    join(sse, "config.yaml"),
    "id: demo-1\nfiles:\n  patch: diffs/patch.diff\n"
  )
  writeFileSync(join(sse, "diffs", "patch.diff"), "from the task folder\n")
  writeFileSync(join(dir, "secret"), "outside the task\n")
  return dir
}

describe("readReferencePatch", () => {
  test("prefers the copy in the run directory", () => {
    const tasks = dataset()
    const results = mkdtempSync(join(tmpdir(), "run-"))
    writeFileSync(join(results, "reference.patch"), "from the run\n")
    const labels = { "ssebench.task-id": "demo-1", [RESULTS_LABEL]: results }
    expect(readReferencePatch(labels, tasks)).toBe("from the run\n")
  })

  test("reads the copy of the run that its label names, among several runs", () => {
    const tasks = dataset()
    const group = mkdtempSync(join(tmpdir(), "group-"))
    for (const id of ["first", "second"]) {
      mkdirSync(join(group, id))
      writeFileSync(join(group, id, "reference.patch"), `from run ${id}\n`)
    }
    const labels = (id: string) => ({
      "ssebench.task-id": "demo-1",
      [RESULTS_LABEL]: join(group, id),
    })
    expect(readReferencePatch(labels("first"), tasks)).toBe("from run first\n")
    expect(readReferencePatch(labels("second"), tasks)).toBe(
      "from run second\n"
    )
  })

  test("falls back to the task folder", () => {
    const tasks = dataset()
    const labels = {
      "ssebench.task-id": "demo-1",
      [RESULTS_LABEL]: join(tasks, "no-such-run"),
    }
    expect(readReferencePatch(labels, tasks)).toBe("from the task folder\n")
  })

  test("stays inside the dataset", () => {
    const tasks = dataset()
    writeFileSync(
      join(tasks, "demo-1", "sse", "config.yaml"),
      "files:\n  patch: ../../secret\n"
    )
    expect(
      readReferencePatch({ "ssebench.task-id": "demo-1" }, tasks)
    ).toBeNull()
    expect(
      readReferencePatch({ "ssebench.task-id": "../demo-1" }, tasks)
    ).toBeNull()
    expect(
      readReferencePatch({ [RESULTS_LABEL]: "relative/dir" }, tasks)
    ).toBeNull()
    expect(readReferencePatch({}, tasks)).toBeNull()
  })
})
