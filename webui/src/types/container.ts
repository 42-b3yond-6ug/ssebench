/**
 * Docker container types for SSEBench WebUI
 */

export interface DockerContainer {
  id: string
  name: string
  taskId: string
  model: string
  agent: string
  status: "running" | "exited" | "paused" | "created"
  image: string
  ports: ContainerPort[]
  createdAt: string
}

export interface ContainerPort {
  host: number
  container: number
  protocol: "tcp" | "udp"
}

/**
 * Raw Docker JSON output from `docker ps --format json`
 */
export interface DockerPsJson {
  ID: string
  Names: string
  Image: string
  Status: string
  Ports: string
  Labels: string
  CreatedAt: string
}

/**
 * API response types
 */
export interface ContainersResponse {
  containers: DockerContainer[]
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
}

/** SDK /result response */
export interface EvaluationResultResponse {
  available: boolean
  patch_result?: PatchResult
  runtime_result?: RuntimeResult
}
