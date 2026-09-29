/**
 * The reference patch of a run, read on the host. The daemon serves it only
 * on its admin socket inside the container, so the web UI reads it from the
 * run directory, where `ssebench run` copies it once the run is over, or else
 * from the task's folder in the local dataset.
 */

import { readFileSync, statSync } from "fs"
import { isAbsolute, join, resolve, sep } from "path"

/** Container label with the run directory on the host */
export const RESULTS_LABEL = "ssebench.results"
const TASK_ID_LABEL = "ssebench.task-id"
const REFERENCE_PATCH_FILE = "reference.patch"
const TASK_ID = /^[A-Za-z0-9][A-Za-z0-9._-]*$/

function readFile(path: string): string | null {
  try {
    return statSync(path).isFile() ? readFileSync(path, "utf-8") : null
  } catch {
    return null
  }
}

/** The patch that `files.patch` names in the task folder's config */
function fromTaskFolder(tasksDir: string, taskId: string): string | null {
  if (!TASK_ID.test(taskId)) return null
  const sse = resolve(tasksDir, taskId, "sse")
  const config = readFile(join(sse, "config.yaml"))
  if (config === null) return null
  let patch: unknown
  try {
    patch = (Bun.YAML.parse(config) as { files?: { patch?: unknown } } | null)
      ?.files?.patch
  } catch {
    return null
  }
  if (typeof patch !== "string") return null
  const file = resolve(sse, patch)
  return file.startsWith(sse + sep) ? readFile(file) : null
}

/**
 * The reference patch of the run in the container with these labels, or
 * null when neither its run directory nor the local dataset has it.
 */
export function readReferencePatch(
  labels: Record<string, string>,
  tasksDir: string
): string | null {
  const results = labels[RESULTS_LABEL]
  if (results && isAbsolute(results)) {
    const patch = readFile(join(results, REFERENCE_PATCH_FILE))
    if (patch !== null) return patch
  }
  const taskId = labels[TASK_ID_LABEL]
  return taskId ? fromTaskFolder(tasksDir, taskId) : null
}
