/**
 * Finished runs, from their run directories.
 *
 * `ssebench run` writes every run to results/<task>/<model>/<agent>/<run-id>/
 * and, when the run is over, `summary.json` in it. That is all this reads, so
 * a run shows with its dialog, diff, grade and reference patch whether or not
 * a container still exists, and on a host that has no backend at all.
 *
 * The agent can write into `archive/` of its run directory, so nothing in it
 * is followed through a link: a link there could point at any file the server
 * can read.
 */

import { lstatSync, readFileSync, realpathSync } from "fs"
import { isAbsolute, join } from "path"
import type {
  ChangedFile,
  DialogEntry,
  DockerContainer,
  EvaluationResultResponse,
  ProjectInfo,
} from "../src/types/container"
import { runCli } from "./runner"

/** A finished run, as `ssebench runs results --json` lists it */
export interface PastRun {
  run_id: string
  task: string
  model: string | null
  agent: string | null
  mode: string | null
  reference_run: boolean
  status: string | null
  started_at: string | null
  /** The run directory, absolute */
  dir: string
}

const LIST_TTL_MS = 3000
const MAX_FILE_BYTES = 32 * 1024 * 1024

let listing: { at: number; result: Promise<PastRun[]> } | null = null

async function fetchPast(): Promise<PastRun[]> {
  const result = await runCli(["runs", "results", "--json"])
  if (result.code !== 0) {
    const lines = result.stderr.trim().split("\n")
    throw new Error(
      `Could not list the finished runs: ${lines[lines.length - 1] || `exit status ${result.code}`}`
    )
  }
  const { runs } = JSON.parse(result.stdout) as { runs?: PastRun[] }
  if (!Array.isArray(runs)) {
    throw new Error("`ssebench runs results --json` printed no list of runs")
  }
  // Two runs can share an ID when different tasks, models or agents reuse
  // it; the newest wins, since the ID is all a URL has to name a run by.
  const newest = new Map<string, PastRun>()
  for (const run of runs) {
    const known = newest.get(run.run_id)
    if (!known || (run.started_at ?? "") > (known.started_at ?? "")) {
      newest.set(run.run_id, run)
    }
  }
  return [...newest.values()]
}

/** The finished runs in results/, newest first. Callers within a moment share one command. */
export function listPastRuns(): Promise<PastRun[]> {
  if (!listing || Date.now() - listing.at > LIST_TTL_MS) {
    const result = fetchPast()
    listing = { at: Date.now(), result }
    result.catch(() => {
      if (listing?.result === result) listing = null
    })
  }
  return listing.result
}

/** Forget the last listing, for tests and after a launch */
export function forgetPastRuns(): void {
  listing = null
}

/** A finished run as the UI lists it */
export function pastToContainer(run: PastRun): DockerContainer {
  return {
    id: run.run_id,
    name: run.run_id,
    taskId: run.task,
    model: run.model || "unknown",
    agent: run.agent || "unknown",
    referenceRun: run.reference_run,
    runId: run.run_id,
    status: "exited",
    image: "",
    createdAt: run.started_at ?? "",
    source: "results",
  }
}

/** The labels a container would have carried, for the code that reads them */
export function pastLabels(run: PastRun): Record<string, string> {
  return {
    "ssebench.run-id": run.run_id,
    "ssebench.task-id": run.task,
    "ssebench.model": run.model ?? "none",
    "ssebench.agent": run.agent ?? "unknown",
    "ssebench.results": run.dir,
    ...(run.reference_run ? { "ssebench.reference-run": "true" } : {}),
  }
}

// =============================================================================
// Files of a run directory
// =============================================================================

/** `path` if it is an absolute path with no `..` in it, else null */
export function plainDir(path: string | null | undefined): string | null {
  return path && isAbsolute(path) && !path.split("/").includes("..")
    ? path
    : null
}

/**
 * The text of a regular file inside a run directory, or null when it is
 * missing, too large, or not a plain file. `name` is a relative path of
 * fixed names; a link at any step of it, or a real path that leaves the
 * directory, makes it unreadable.
 */
export function readRunFile(dir: string, name: string): string | null {
  if (!isAbsolute(dir)) return null
  try {
    const path = join(dir, name)
    let step = dir
    for (const part of name.split("/")) {
      step = join(step, part)
      if (lstatSync(step).isSymbolicLink()) return null
    }
    const info = lstatSync(path)
    if (!info.isFile() || info.size > MAX_FILE_BYTES) return null
    const real = realpathSync(path)
    const root = realpathSync(dir)
    if (real !== join(root, name)) return null
    return readFileSync(real, "utf-8")
  } catch {
    return null
  }
}

function readJson(dir: string, name: string): Record<string, unknown> | null {
  const text = readRunFile(dir, name)
  if (text === null || !text.trim()) return null
  try {
    const value: unknown = JSON.parse(text)
    return typeof value === "object" && value !== null && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : null
  } catch {
    return null
  }
}

/** The task's metadata as the daemon's /project reports it, from the summary the CLI wrote */
export function readProject(dir: string): ProjectInfo | null {
  const task = readJson(dir, "summary.json")?.task as
    | Record<string, unknown>
    | undefined
  if (!task || typeof task.id !== "string") return null
  const files = task.files as { poc?: unknown } | undefined
  const description = task.task_description as
    | ProjectInfo["task_description"]
    | undefined
  return {
    id: task.id,
    project: typeof task.project === "string" ? task.project : task.id,
    language: typeof task.language === "string" ? task.language : "",
    source: typeof task.source === "string" ? task.source : "",
    task_description: description ?? {},
    poc: Array.isArray(files?.poc)
      ? files.poc.filter((p): p is string => typeof p === "string")
      : [],
  }
}

/** The grade in result.json, as the daemon's /result reports it */
export function readGrade(dir: string): EvaluationResultResponse | null {
  const grade = readJson(dir, "result.json")
  if (
    !grade ||
    typeof grade.patch_result !== "object" ||
    grade.patch_result === null ||
    typeof grade.runtime_result !== "object" ||
    grade.runtime_result === null
  ) {
    return null
  }
  return {
    available: true,
    patch_result: grade.patch_result as never,
    runtime_result: grade.runtime_result as never,
  }
}

/** The patch the grader applied, or an empty patch when the agent changed nothing */
export function readDiff(dir: string): string | null {
  return readRunFile(dir, "final.patch")
}

/**
 * The files a unified diff changes, with the lines it adds and removes, as
 * the daemon's /files reports them.
 */
export function parseDiffFiles(diff: string): ChangedFile[] {
  const files: ChangedFile[] = []
  let current: ChangedFile | null = null
  let inHunk = false
  for (const line of diff.split("\n")) {
    const header = /^diff --git a\/(.+?) b\/(.+)$/.exec(line)
    if (header) {
      current = {
        path: header[2],
        status: "modified",
        additions: 0,
        deletions: 0,
      }
      files.push(current)
      inHunk = false
    } else if (current) {
      if (line.startsWith("@@")) inHunk = true
      else if (!inHunk) {
        if (line.startsWith("new file mode")) current.status = "added"
        else if (line.startsWith("deleted file mode"))
          current.status = "deleted"
        else if (line.startsWith("rename from ")) current.status = "renamed"
      } else if (line.startsWith("+")) current.additions++
      else if (line.startsWith("-")) current.deletions++
    }
  }
  return files
}

const MAX_DIALOG_ENTRIES = 200_000

/**
 * The entries of the agent's dialog whose `seq` is greater than `since`, in
 * file order. Lines that are not JSON or have no `seq` are skipped, as the
 * daemon skips them.
 */
export function readDialog(dir: string, since = -1): DialogEntry[] | null {
  const text = readRunFile(dir, "archive/dialog.jsonl")
  if (text === null) return null
  const entries: DialogEntry[] = []
  for (const line of text.split("\n")) {
    if (!line.trim()) continue
    try {
      const entry = JSON.parse(line) as DialogEntry
      if (typeof entry.seq === "number" && entry.seq > since) {
        entries.push(entry)
        if (entries.length >= MAX_DIALOG_ENTRIES) break
      }
    } catch {
      // not an entry
    }
  }
  return entries
}

/** The output of the run's container that the run directory keeps, for the log view */
export function readLogText(dir: string): string {
  const parts: string[] = []
  for (const name of ["agent.log", "evaluator.log"]) {
    const text = readRunFile(dir, name)
    if (text?.trim()) parts.push(`==> ${name} <==\n${text}`)
  }
  return parts.join("\n")
}
