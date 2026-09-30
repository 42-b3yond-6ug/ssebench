/**
 * How a run's state is worded, for the lists.
 */

import type { DockerContainer } from "../types/container"

const LABELS: Record<DockerContainer["status"], string> = {
  running: "Running",
  exited: "Exited",
  paused: "Paused",
  created: "Created",
  unknown: "Unknown",
}

/**
 * The label of a run's state. A finished run that only its results directory
 * remembers is "Finished" rather than stopped: nothing was stopped, and it
 * has no container.
 */
export function statusLabel(
  container: DockerContainer,
  exited = LABELS.exited
): string {
  if (container.source === "results") return "Finished"
  return container.status === "exited" ? exited : LABELS[container.status]
}
