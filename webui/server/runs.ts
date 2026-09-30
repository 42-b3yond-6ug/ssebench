/**
 * The runs the UI shows: those on the backend, and those that only their
 * run directory remembers.
 *
 * A run the backend still has is the live one, with a container to talk to.
 * A finished run whose container is gone is read from its run directory, and
 * is read-only. A run that has both is the live one, and its directory backs
 * it up once the container has stopped.
 */

import type { DockerContainer } from "../src/types/container"
import {
  listPastRuns,
  pastLabels,
  plainDir,
  pastToContainer,
  type PastRun,
} from "./pastRuns"
import { listRuns, toContainer, isRunId, type RunnerRun } from "./runner"

/** A run request-supplied ID names */
export interface ResolvedRun {
  /** The run ID */
  id: string
  /** `container` when the backend has the run, `results` when only its directory remains */
  source: "container" | "results"
  status: DockerContainer["status"]
  /** The labels of the container, or those it would have carried */
  labels: Record<string, string>
  /** The run directory, when the labels or the results listing name one */
  resultsDir: string | null
}

function fromLive(run: RunnerRun): ResolvedRun {
  return {
    id: run.run_id,
    source: "container",
    status: toContainer(run).status,
    labels: run.labels,
    resultsDir: plainDir(run.results_dir),
  }
}

function fromPast(run: PastRun): ResolvedRun {
  return {
    id: run.run_id,
    source: "results",
    status: "exited",
    labels: pastLabels(run),
    resultsDir: run.dir,
  }
}

/**
 * The run with this ID: on the backend, else in results/. Null for a
 * malformed ID and for a run neither has.
 */
export async function resolveRun(id: string): Promise<ResolvedRun | null> {
  if (!isRunId(id)) return null
  let live: RunnerRun | undefined
  try {
    live = (await listRuns()).runs.find((run) => run.run_id === id)
  } catch {
    // A host without a working backend can still show finished runs
  }
  if (live) {
    const run = fromLive(live)
    if (!run.resultsDir) {
      // The backend does not say where the run wrote, but results/ may know
      const past = (await pastRuns()).find((p) => p.run_id === id)
      if (past) {
        run.resultsDir = past.dir
        run.labels = { ...run.labels, "ssebench.results": past.dir }
      }
    }
    return run
  }
  const past = (await pastRuns()).find((p) => p.run_id === id)
  return past ? fromPast(past) : null
}

async function pastRuns(): Promise<PastRun[]> {
  try {
    return await listPastRuns()
  } catch (error) {
    console.error(error instanceof Error ? error.message : error)
    return []
  }
}

export interface RunListing {
  containers: DockerContainer[]
  /** Why the backend's runs are missing from the list, when they are */
  runnerError?: string
}

/**
 * Every run: the backend's, newest first, then the finished runs it no
 * longer has. If the backend cannot be reached the finished runs are still
 * listed, with the reason.
 */
export async function listContainers(): Promise<RunListing> {
  const [live, past] = await Promise.all([
    listRuns().then(
      (list) => ({ list }),
      (error: unknown) => ({ error })
    ),
    pastRuns(),
  ])
  const containers: DockerContainer[] = []
  const seen = new Set<string>()
  if ("list" in live) {
    for (const run of live.list.runs) {
      if (!run.run_id || seen.has(run.run_id)) continue
      seen.add(run.run_id)
      containers.push(toContainer(run))
    }
  }
  for (const run of past) {
    if (seen.has(run.run_id)) continue
    seen.add(run.run_id)
    containers.push(pastToContainer(run))
  }
  if ("error" in live) {
    return {
      containers,
      runnerError:
        live.error instanceof Error ? live.error.message : String(live.error),
    }
  }
  return { containers }
}

/** One run as the UI lists it, or null */
export async function getContainer(
  id: string
): Promise<DockerContainer | null> {
  const { containers } = await listContainers()
  return containers.find((c) => c.id === id) ?? null
}
