/**
 * The data of the static showcase: what a hosted server would answer for
 * finished runs, written as JSON files.
 *
 * Every value comes from the readers the server itself uses (pastRuns.ts,
 * reference.ts), so the files hold what `SSEBENCH_WEBUI_HOSTED=1` serves for
 * the same results/ directory, with the same size caps and the same refusal to
 * follow links inside a run directory. The client reads them in static mode
 * (src/lib/staticSite.ts).
 *
 * Layout under the output directory, with no path that is both a file and a
 * directory:
 *   data/health.json        what /api/health answers
 *   data/runs.json          what /api/containers answers
 *   data/runs/<run-id>.json one StaticRunData per run
 */

import { mkdirSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { version } from "../package.json"
import type { StaticRunData } from "../src/types/container"
import {
  fetchPast,
  parseDiffFiles,
  pastLabels,
  pastToContainer,
  readDialog,
  readDiff,
  readGrade,
  readLogText,
  readProject,
  readReview,
  type PastRun,
} from "./pastRuns"
import { readReferencePatch } from "./reference"
import { isRunId } from "./runner"

/** What /api/health answers: a hosted server whose "runner" is the exported files, so the UI shows no warning */
export function staticHealth(now = new Date()) {
  return {
    status: "ok",
    version,
    runner: true,
    backend: "static",
    terminal: false,
    assistant: false,
    hosted: true,
    timestamp: now.toISOString(),
  }
}

/** The view data of one finished run, as the hosted server serves it */
export function staticRunData(run: PastRun, tasksDir: string): StaticRunData {
  const diff = readDiff(run.dir)
  return {
    container: pastToContainer(run),
    project: readProject(run.dir),
    diff,
    files: diff === null ? [] : parseDiffFiles(diff),
    dialog: readDialog(run.dir) ?? [],
    result: readGrade(run.dir),
    referencePatch: readReferencePatch(pastLabels(run), tasksDir) ?? "",
    review: readReview(run.dir),
    logs: readLogText(run.dir),
  }
}

export interface ExportOptions {
  /** Where `ssebench runs results --json` looks, absolute; its default without one */
  resultsDir?: string
  /** The local dataset, for a reference patch the run directory lacks */
  tasksDir: string
  now?: Date
}

export interface ExportSummary {
  runs: number
}

/** The finished runs of results/, newest first, one per run ID, as the server lists them */
async function listRuns(resultsDir?: string): Promise<PastRun[]> {
  const found = await fetchPast(resultsDir)
  // `fetchPast` keeps the newest run per ID, as the server does; an ID the
  // server would refuse in a URL has no page, so it has no file either.
  return found.filter((run) => isRunId(run.run_id))
}

/** Write the JSON files under `outDir` */
export async function exportStaticData(
  outDir: string,
  options: ExportOptions
): Promise<ExportSummary> {
  const runs = await listRuns(options.resultsDir)
  const dataDir = join(outDir, "data")
  mkdirSync(join(dataDir, "runs"), { recursive: true })
  const write = (path: string, value: unknown) =>
    writeFileSync(path, JSON.stringify(value))

  write(join(dataDir, "health.json"), staticHealth(options.now))
  write(join(dataDir, "runs.json"), {
    containers: runs.map(pastToContainer),
  })
  for (const run of runs) {
    write(
      join(dataDir, "runs", `${run.run_id}.json`),
      staticRunData(run, options.tasksDir)
    )
  }
  return { runs: runs.length }
}
