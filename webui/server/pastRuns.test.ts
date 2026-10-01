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
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import {
  listPastRuns,
  forgetPastRuns,
  parseDiffFiles,
  pastLabels,
  pastToContainer,
  readDialog,
  readDiff,
  readGrade,
  readLogText,
  readProject,
  readReview,
  readRunFile,
} from "./pastRuns"
import { createFakes, pastJson, setState, type Fakes } from "./testing"

let root: string
let fakes: Fakes
const savedEnv: Record<string, string | undefined> = {}

beforeAll(() => {
  root = mkdtempSync(join(tmpdir(), "past-runs-"))
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
  rmSync(root, { recursive: true, force: true })
  rmSync(fakes.dir, { recursive: true, force: true })
})

beforeEach(forgetPastRuns)

/** A run directory the way `ssebench run` leaves one */
function runDir(name: string): string {
  const dir = join(root, name)
  mkdirSync(join(dir, "archive"), { recursive: true })
  return dir
}

const DIFF = `diff --git a/gjson.go b/gjson.go
index 111..222 100644
--- a/gjson.go
+++ b/gjson.go
@@ -1,3 +1,4 @@
 keep
-old
+new
+more
diff --git a/added.txt b/added.txt
new file mode 100644
--- /dev/null
+++ b/added.txt
@@ -0,0 +1 @@
+--- looks like a header
diff --git a/gone.txt b/gone.txt
deleted file mode 100644
--- a/gone.txt
+++ /dev/null
@@ -1,2 +0,0 @@
-a
-b
diff --git a/old.txt b/new.txt
similarity index 90%
rename from old.txt
rename to new.txt
`

describe("parseDiffFiles", () => {
  test("counts lines and tells added, deleted and renamed files apart", () => {
    expect(parseDiffFiles(DIFF)).toEqual([
      { path: "gjson.go", status: "modified", additions: 2, deletions: 1 },
      { path: "added.txt", status: "added", additions: 1, deletions: 0 },
      { path: "gone.txt", status: "deleted", additions: 0, deletions: 2 },
      { path: "new.txt", status: "renamed", additions: 0, deletions: 0 },
    ])
  })

  test("an empty patch changes no file", () => {
    expect(parseDiffFiles("")).toEqual([])
  })
})

describe("readRunFile", () => {
  test("reads a plain file of the run directory", () => {
    const dir = runDir("plain")
    writeFileSync(join(dir, "final.patch"), DIFF)
    expect(readDiff(dir)).toBe(DIFF)
  })

  test("is null for a missing file and a relative directory", () => {
    const dir = runDir("missing")
    expect(readRunFile(dir, "final.patch")).toBeNull()
    expect(readRunFile("relative/dir", "final.patch")).toBeNull()
  })

  test("does not follow a link the agent planted in archive/", () => {
    const secret = join(root, "secret.jsonl")
    writeFileSync(
      secret,
      '{"seq": 1, "type": "message", "content": "secret"}\n'
    )
    const dir = runDir("linked-file")
    symlinkSync(secret, join(dir, "archive", "dialog.jsonl"))
    expect(readDialog(dir)).toBeNull()

    // or replaced archive/ itself
    const other = runDir("linked-dir")
    rmSync(join(other, "archive"), { recursive: true })
    const elsewhere = join(root, "elsewhere")
    mkdirSync(elsewhere)
    writeFileSync(join(elsewhere, "dialog.jsonl"), '{"seq": 1}\n')
    symlinkSync(elsewhere, join(other, "archive"))
    expect(readDialog(other)).toBeNull()
  })

  test("does not read something that is not a file", () => {
    const dir = runDir("odd")
    mkdirSync(join(dir, "final.patch"))
    expect(readDiff(dir)).toBeNull()
  })
})

describe("readDialog", () => {
  test("returns the entries after `since`, and skips lines that are not entries", () => {
    const dir = runDir("dialog")
    writeFileSync(
      join(dir, "archive", "dialog.jsonl"),
      [
        '{"seq": 0, "type": "init"}',
        "not json",
        '{"type": "message"}',
        '{"seq": 1, "type": "message", "content": "hi"}',
        "",
        '{"seq": 2, "type": "message"}',
      ].join("\n")
    )
    expect(readDialog(dir)?.map((e) => e.seq)).toEqual([0, 1, 2])
    expect(readDialog(dir, 0)?.map((e) => e.seq)).toEqual([1, 2])
    expect(readDialog(dir, 2)).toEqual([])
  })

  test("is null for a run that wrote no dialog", () => {
    expect(readDialog(runDir("no-dialog"))).toBeNull()
  })
})

describe("readReview", () => {
  test("reads the note beside summary.json", () => {
    const dir = runDir("review")
    writeFileSync(join(dir, "post-review.txt"), "Line one\n  indented <b>\n")
    expect(readReview(dir)).toEqual({
      available: true,
      text: "Line one\n  indented <b>\n",
    })
  })

  test("is unavailable when the note is missing or blank", () => {
    const dir = runDir("no-review")
    expect(readReview(dir)).toEqual({ available: false })
    writeFileSync(join(dir, "post-review.txt"), " \n")
    expect(readReview(dir)).toEqual({ available: false })
  })

  test("does not follow a link in place of the note", () => {
    const secret = join(root, "secret.txt")
    writeFileSync(secret, "secret")
    const dir = runDir("linked-review")
    symlinkSync(secret, join(dir, "post-review.txt"))
    expect(readReview(dir)).toEqual({ available: false })
  })
})

describe("readProject and readGrade", () => {
  test("build the daemon's answers from the summary and the grade", () => {
    const dir = runDir("summary")
    writeFileSync(
      join(dir, "summary.json"),
      JSON.stringify({
        task: {
          id: "demo-1",
          project: "demo",
          language: "go",
          source: "/src/demo",
          task_description: { crash_report: ["reports/crash.txt"] },
          files: { poc: ["pocs/poc.go"] },
          reference: ["https://example.org"],
        },
      })
    )
    writeFileSync(
      join(dir, "result.json"),
      JSON.stringify({
        patch_result: { status: "passed" },
        runtime_result: { agent_duration: 3 },
        config: { agent: "dummy" },
      })
    )

    expect(readProject(dir)).toEqual({
      id: "demo-1",
      project: "demo",
      language: "go",
      source: "/src/demo",
      task_description: { crash_report: ["reports/crash.txt"] },
      poc: ["pocs/poc.go"],
    })
    expect(readGrade(dir)).toEqual({
      available: true,
      patch_result: { status: "passed" },
      runtime_result: { agent_duration: 3 },
    } as never)
  })

  test("are null when the files are missing or are not what they should be", () => {
    const dir = runDir("damaged")
    expect(readProject(dir)).toBeNull()
    expect(readGrade(dir)).toBeNull()
    for (const content of ["", "{", "[]", '{"patch_result": 1}', '{"a": 1}']) {
      writeFileSync(join(dir, "result.json"), content)
      expect(readGrade(dir)).toBeNull()
    }
    writeFileSync(join(dir, "summary.json"), '{"task": {"project": "x"}}')
    expect(readProject(dir)).toBeNull()
  })
})

describe("readLogText", () => {
  test("joins the logs the run directory keeps", () => {
    const dir = runDir("logs")
    writeFileSync(join(dir, "agent.log"), "agent said\n")
    writeFileSync(join(dir, "evaluator.log"), "graded\n")
    writeFileSync(join(dir, "daemon.log"), "not shown\n")
    expect(readLogText(dir)).toBe(
      "==> agent.log <==\nagent said\n\n==> evaluator.log <==\ngraded\n"
    )
    expect(readLogText(runDir("no-logs"))).toBe("")
  })
})

describe("listing", () => {
  test("lists what the CLI finds, one run for each ID, the newest first", async () => {
    setState(fakes, {
      past: [
        pastJson("new", "/r/new", { started_at: "2026-02-01T00:00:00Z" }),
        pastJson("old", "/r/old", { started_at: "2026-01-01T00:00:00Z" }),
        pastJson("new", "/r/other-task/new", {
          task: "demo-task-2",
          started_at: "2026-01-15T00:00:00Z",
        }),
      ],
    })

    const runs = await listPastRuns()

    expect(runs.map((r) => [r.run_id, r.dir])).toEqual([
      ["new", "/r/new"],
      ["old", "/r/old"],
    ])
  })

  test("shows a finished run as an exited one with no container", () => {
    const run = pastJson("r1", "/r/r1", {
      model: "none",
      agent: "reference",
      reference_run: true,
    }) as never
    expect(pastToContainer(run)).toMatchObject({
      id: "r1",
      runId: "r1",
      status: "exited",
      source: "results",
      referenceRun: true,
      agent: "reference",
      model: "none",
    })
    expect(pastLabels(run)).toMatchObject({
      "ssebench.run-id": "r1",
      "ssebench.results": "/r/r1",
      "ssebench.reference-run": "true",
    })
  })
})
