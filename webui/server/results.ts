/**
 * The grade of a run, read from its results directory on the host.
 *
 * The daemon in a task container serves the grade that the evaluator wrote to
 * the run's results directory. This reads the same file on the host, where
 * `ssebench run` mounts the directory from, so a grade also shows for a
 * container that has stopped, whose daemon no longer answers.
 */

import { existsSync, readFileSync, statSync } from "fs"
import { isAbsolute, join } from "path"
import type { EvaluationResultResponse } from "../src/types/container"
import { ssebenchPath } from "./config"
import { resolveContainer } from "./docker"
import { RESULTS_LABEL } from "./reference"

const MAX_RESULT_BYTES = 8 * 1024 * 1024
/** A results directory is results/<task>/<model>/<agent>; each part is a name */
const NAME = /^[A-Za-z0-9][A-Za-z0-9._-]*$/

/** Split a model name such as `provider/model` into path-safe parts */
function parts(value: string | undefined): string[] | null {
  if (!value) return null
  const names = value.split("/")
  return names.every((n) => NAME.test(n)) ? names : null
}

/**
 * Where the run of a container wrote its results: the directory its label
 * names, else results/<task>/<model>/<agent> in the checkout, which is where
 * a run started from the web UI writes them (for a container made before the
 * label existed). Null when the labels do not say, or say something that is
 * not a plain path.
 */
export function resultsDir(
  labels: Record<string, string>,
  checkout = ssebenchPath()
): string | null {
  const labelled = labels[RESULTS_LABEL]
  if (labelled) {
    return isAbsolute(labelled) && !labelled.split("/").includes("..")
      ? labelled
      : null
  }
  const task = parts(labels["ssebench.task-id"])
  const model = parts(labels["ssebench.model"])
  const agent = parts(labels["ssebench.agent"])
  if (!task || !model || !agent) return null
  return join(checkout, "results", ...task, ...model, ...agent)
}

/**
 * The evaluation result that the run wrote, in the shape of the daemon's
 * /result, or null while there is none, or none that parses.
 */
export function readGrade(
  labels: Record<string, string>,
  checkout = ssebenchPath()
): EvaluationResultResponse | null {
  const dir = resultsDir(labels, checkout)
  if (!dir) return null
  const file = join(dir, "result.json")
  try {
    if (!existsSync(file) || statSync(file).size > MAX_RESULT_BYTES) {
      return null
    }
    const text = readFileSync(file, "utf-8").trim()
    if (!text) return null
    const grade = JSON.parse(text) as Record<string, unknown>
    if (
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
  } catch {
    return null
  }
}

/**
 * The grade of a container: the daemon's if it has one, else the run's from
 * the host. The daemon has none for a sidecar run, and none once the
 * container has stopped.
 */
export async function gradeOf(
  containerId: string,
  fromDaemon: EvaluationResultResponse | null
): Promise<EvaluationResultResponse | null> {
  if (fromDaemon?.available) return fromDaemon
  const container = await resolveContainer(containerId)
  return (container && readGrade(container.labels)) ?? fromDaemon
}
