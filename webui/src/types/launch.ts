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

/** Network egress of the run container */
export type Egress = "restricted" | "open"

/** Launch configuration submitted by user */
export interface LaunchConfig {
  task: string
  /** Absent for the reference agent, which makes no model calls */
  model?: string
  agent: string
  mode: LaunchMode
  source: TaskSource
  /** Seconds the agent may run; the CLI default when absent */
  timeout?: number
  /** 0 to 4; the CLI default when absent */
  difficulty?: number
  egress?: Egress
  /** Plugins to run instead of those plugins.yaml enables */
  plugins?: string[]
}

/** A plugin declared in plugins.yaml */
export interface PluginInfo {
  name: string
  /** plugins.yaml runs it in every run */
  enabled: boolean
  hook: string
  llm: boolean
}

/** The CLI's `doctor --json`, as the server relays it */
export type DoctorResult =
  | {
      available: true
      report: {
        checks: {
          name: string
          status: "ok" | "warn" | "fail"
          detail: string
          fix: string
        }[]
        /** By model: the provider keys it needs, and those .env lacks */
        models: Record<string, { keys: string[]; missing: string[] }>
      }
    }
  | { available: false; error: string }

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
  plugins: PluginInfo[]
}
