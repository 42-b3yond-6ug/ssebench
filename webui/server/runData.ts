/**
 * What the UI asks of a run: its task, diff, changed files, dialog and grade.
 *
 * A running run answers through its daemon, at the URL the backend gives. A
 * run that has stopped, or that only its run directory remembers, answers
 * from the files it left, which hold the same things; so the view of a
 * finished run does not depend on a container being there.
 */

import { forgetEndpoint, getSDKUrl } from "./runner"
import { resolveRun, type ResolvedRun } from "./runs"
import {
  parseDiffFiles,
  readDiff,
  readDialog,
  readGrade,
  readProject,
} from "./pastRuns"

export interface RunResponse {
  data: unknown
  status: number
}

/** Whether the run's daemon is the place to ask: the run has a container that is not known to be over */
export function usesDaemon(run: ResolvedRun): boolean {
  return (
    run.source === "container" &&
    (run.status === "running" || run.status === "unknown")
  )
}

/** Answer a daemon endpoint (`/project`, `/diff`, `/files`, `/agent/dialog?since=N`, `/result`) from the run directory, or null when it has none */
export function answerFromFiles(
  run: ResolvedRun,
  endpoint: string
): RunResponse | null {
  const dir = run.resultsDir
  if (!dir) return null
  const url = new URL(endpoint, "http://run")
  switch (url.pathname) {
    case "/project": {
      const project = readProject(dir)
      return project ? { data: project, status: 200 } : null
    }
    case "/diff": {
      const diff = readDiff(dir)
      return diff === null ? null : { data: { diff }, status: 200 }
    }
    case "/files": {
      const diff = readDiff(dir)
      return diff === null
        ? null
        : { data: { files: parseDiffFiles(diff) }, status: 200 }
    }
    case "/agent/dialog": {
      const since = url.searchParams.get("since")
      const entries = readDialog(dir, since === null ? -1 : Number(since))
      // The daemon answers with no entries for a run that wrote no dialog
      return { data: { entries: entries ?? [] }, status: 200 }
    }
    case "/result": {
      const grade = readGrade(dir)
      return {
        data: grade ?? { available: false },
        status: 200,
      }
    }
    default:
      return null
  }
}

/** Ask the run's daemon for `endpoint` */
async function askDaemon(id: string, endpoint: string): Promise<RunResponse> {
  const sdkUrl = await getSDKUrl(id)
  if (!sdkUrl) {
    return {
      data: { error: "SDK not accessible - the run may not be running" },
      status: 503,
    }
  }
  try {
    const response = await fetch(`${sdkUrl}${endpoint}`, {
      signal: AbortSignal.timeout(5000),
    })
    return { data: await response.json(), status: response.status }
  } catch (error) {
    console.error(`SDK proxy failed for ${sdkUrl}${endpoint}:`, error)
    // The address may have changed, for example because the run restarted
    forgetEndpoint(id)
    if (error instanceof Error && error.name === "TimeoutError") {
      return { data: { error: "SDK request timeout" }, status: 504 }
    }
    return {
      data: { error: "Failed to communicate with SDK daemon" },
      status: 500,
    }
  }
}

/**
 * The answer to a request for `endpoint` of run `id`: from its daemon while it
 * runs, otherwise from its run directory.
 */
export async function runData(
  id: string,
  endpoint: string
): Promise<RunResponse> {
  const run = await resolveRun(id)
  if (!run) return { data: { error: "Run not found" }, status: 404 }
  if (usesDaemon(run)) return askDaemon(id, endpoint)
  return (
    answerFromFiles(run, endpoint) ?? {
      data: { error: "The run is over and left nothing to show for this" },
      status: 404,
    }
  )
}
