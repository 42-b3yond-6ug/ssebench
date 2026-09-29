/**
 * Launch Types - Task launcher for SSEBench WebUI
 */

/** A benchmark task */
export interface Task {
  id: string
  language?: string
  project?: string
}

/** Task source selection */
export type TaskSource = "local" | "remote"

/** Execution mode */
export type LaunchMode = "sandbox" | "sidecar"

/** Launch configuration submitted by user */
export interface LaunchConfig {
  task: string
  model: string
  agent: string
  mode: LaunchMode
  source: TaskSource
  timeout?: number
  difficulty?: number
}

/** Launch status response from backend */
export interface LaunchStatus {
  launch_id: string
  status: "launching" | "running" | "failed"
  containerId?: string
  error?: string
  command: string
  taskId: string
  startTime: string
}

/** Launch configuration info from backend */
export interface LaunchConfigInfo {
  hasLocalBenchmarks: boolean
  catalogConfigured: boolean
  modes: LaunchMode[]
}
