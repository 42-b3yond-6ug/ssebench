/**
 * The grade of a run, read from its results directory on the host.
 *
 * The daemon in a task container serves the grade that the evaluator wrote to
 * the run's results directory. This reads the same file on the host, where
 * `ssebench run` mounts the directory from, so a grade also shows for a
 * container that has stopped, whose daemon no longer answers.
 */

import type { EvaluationResultResponse } from "../src/types/container"
import { plainDir, readGrade as readGradeFile } from "./pastRuns"
import { RESULTS_LABEL } from "./reference"
import { resolveRun } from "./runs"

/**
 * Where the run wrote its results: its own run directory,
 * results/<task>/<model>/<agent>/<run-id>, which the `ssebench.results` label
 * names. Null when the labels do not say, or say something that is not a
 * plain absolute path.
 */
export function resultsDir(labels: Record<string, string>): string | null {
  return plainDir(labels[RESULTS_LABEL])
}

/**
 * The evaluation result that the run wrote, in the shape of the daemon's
 * /result, or null while there is none, or none that parses.
 */
export function readGrade(
  labels: Record<string, string>
): EvaluationResultResponse | null {
  const dir = resultsDir(labels)
  return dir ? readGradeFile(dir) : null
}

/**
 * The grade of a run: the daemon's if it has one, else the run's from the
 * host. The daemon has none for a sidecar run, and none once the container
 * has stopped.
 */
export async function gradeOf(
  runId: string,
  fromDaemon: EvaluationResultResponse | null
): Promise<EvaluationResultResponse | null> {
  if (fromDaemon?.available) return fromDaemon
  const run = await resolveRun(runId)
  return (run && readGrade(run.labels)) ?? fromDaemon
}
