/**
 * Run types for SSEBench WebUI
 */

/**
 * A run as the server lists it: the container of a run on the backend, or a
 * finished run that only its results directory remembers. `id` is the run ID,
 * whichever backend carries it.
 */
export interface DockerContainer {
  id: string
  name: string
  taskId: string
  model: string
  agent: string
  /** The reference agent applied the task's known fix: the grade rates the task, not a model */
  referenceRun: boolean
  /** The run ID: `--run-id`, or the one the CLI made */
  runId: string
  status: "running" | "exited" | "paused" | "created" | "unknown"
  image: string
  createdAt: string
  /**
   * `container` for a run the backend has; `results` for a finished run read
   * from its run directory, which has no container to stop, open or ask.
   */
  source: "container" | "results"
}

/**
 * API response types
 */
export interface ContainersResponse {
  containers: DockerContainer[]
  /** Why the backend's runs are missing, when the server could not list them */
  runnerError?: string
}

/**
 * SDK API types - Data from SDK daemon inside containers
 */

/** Task description from config.yaml */
export interface TaskDescription {
  issue?: string
  crash_report?: string[]
  bug_description?: string
}

/** Project metadata from SDK /project endpoint */
export interface ProjectInfo {
  id: string
  project: string
  language: string
  source: string
  task_description: TaskDescription
  poc: string[]
}

/** Changed file from SDK /files endpoint */
export interface ChangedFile {
  path: string
  status: "modified" | "added" | "deleted" | "renamed"
  additions: number
  deletions: number
}

/** SDK /files response */
export interface FilesResponse {
  files: ChangedFile[]
}

/** SDK /diff response */
export interface DiffResponse {
  diff: string
}

/** SDK health check response */
export interface SDKHealthResponse {
  healthy: boolean
  sdkUrl?: string
  reason?: string
}

/** SDK version response */
export interface SDKVersionResponse {
  version: string
}

// =============================================================================
// Agent Dialog Types - Real-time agent conversation log
// =============================================================================

/** Base interface for all dialog entries */
interface DialogEntryBase {
  seq: number
  ts: string
}

/** Session initialization entry */
export interface InitEntry extends DialogEntryBase {
  type: "init"
  data: {
    task: string
    cwd: string
    model: string
    agent: string
  }
}

/** User prompt entry (the task given to the agent) */
export interface PromptEntry extends DialogEntryBase {
  type: "prompt"
  content: string
}

/** Assistant message entry */
export interface MessageEntry extends DialogEntryBase {
  type: "message"
  role: "assistant"
  content: string
  tokens?: {
    in: number
    out: number
  }
}

/** Thinking/reasoning entry (collapsible in UI) */
export interface ThinkingEntry extends DialogEntryBase {
  type: "thinking"
  content: string
}

/** Tool call entry - tracks tool execution status */
export interface ToolEntry extends DialogEntryBase {
  type: "tool"
  tool_id: string
  name: string
  status: "running" | "success" | "error"
  args?: Record<string, unknown>
  result?: string
  error?: string
}

/** Session completion entry */
export interface CompleteEntry extends DialogEntryBase {
  type: "complete"
  status: "success" | "error" | "timeout"
  turns: number
  duration_ms: number
  total_tokens: {
    in: number
    out: number
  }
  message?: string
}

/** Union type for all dialog entries */
export type DialogEntry =
  | InitEntry
  | PromptEntry
  | MessageEntry
  | ThinkingEntry
  | ToolEntry
  | CompleteEntry

/** SDK /agent/dialog response */
export interface DialogResponse {
  entries: DialogEntry[]
}

// =============================================================================
// Evaluation Result Types - Result after agent finishes
// =============================================================================

/** Patch evaluation result */
export interface PatchResult {
  /** `error`: not graded, or the agent failed and the model answered no call. Absent from older results. */
  status?: "passed" | "failed" | "error"
  build_success: boolean | null
  pov_passed: number | null
  pov_total: number | null
  func_test_success: boolean | null
  intent_test_success: boolean | null
  error_msg: string | null
  error_log: string | null
}

/** Runtime statistics */
export interface RuntimeResult {
  agent_duration: number
  agent_timeout: boolean
  evaluator_timeout: boolean
  /** The agent's exit status; absent or null when it was not recorded. */
  agent_exit_code?: number | null
}

/** A reviewer's note on a finished run, from its `post-review.txt` */
export type ReviewResponse =
  { available: true; text: string } | { available: false }

/** SDK /result response */
export interface EvaluationResultResponse {
  available: boolean
  patch_result?: PatchResult
  runtime_result?: RuntimeResult
}

/**
 * Everything the run view needs for one finished run, as the static export
 * writes it to data/runs/<run-id>.json (see server/staticExport.ts).
 */
export interface StaticRunData {
  container: DockerContainer
  project: ProjectInfo | null
  /** The patch the grader applied; null when the run left none */
  diff: string | null
  files: ChangedFile[]
  dialog: DialogEntry[]
  result: EvaluationResultResponse | null
  referencePatch: string
  review: ReviewResponse
  /** The component logs the run directory keeps, as the log view shows them */
  logs: string
}
