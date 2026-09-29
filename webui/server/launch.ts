/**
 * Launch Module - Task launcher for SSEBench
 *
 * Supports multiple concurrent launches, each tracked independently.
 *
 * Handles:
 * - Fetching available tasks (local/remote), models, and agents
 * - Spawning benchmark subprocesses
 * - Tracking launch status per launch_id
 * - Broadcasting tagged status/log messages over WebSocket
 */

import { spawn, type Subprocess } from "bun"
import { readdirSync, readFileSync, existsSync } from "fs"
import { join } from "path"
import { listContainers } from "./docker"

// =============================================================================
// Configuration
// =============================================================================

// Root of the SSEBench checkout: `uv run ssebench` runs here, and models/
// and agents/ are read from here. The webui lives in webui/ at that root.
const SSEBENCH_PATH =
  process.env.SSEBENCH_PATH || join(import.meta.dir, "..", "..")
const LOCAL_TASKS_PATH =
  process.env.SSEBENCH_LOCAL_TASKS || join(SSEBENCH_PATH, "datasets", "pilot")
const MODELS_PATH = join(SSEBENCH_PATH, "models")
const AGENTS_PATH = join(SSEBENCH_PATH, "agents")

// Base URL of a task catalog service (serves GET /tasks). There is no
// default: without it only local tasks can be listed and launched.
const CATALOG_URL =
  process.env.SSEBENCH_CATALOG_URL?.trim().replace(/\/+$/, "") || null

export const CATALOG_NOT_CONFIGURED =
  "Task catalog not configured: set SSEBENCH_CATALOG_URL for the webui server"

// =============================================================================
// Types
// =============================================================================

interface Task {
  id: string
  language?: string
  project?: string
}

export interface LaunchConfig {
  task: string
  model: string
  agent: string
  mode: "sandbox" | "sidecar"
  source: "local" | "remote"
  timeout?: number
  difficulty?: number
}

interface LaunchStatus {
  launch_id: string
  status: "launching" | "running" | "failed"
  containerId?: string
  error?: string
  command: string
  taskId: string
  startTime: string
}

// =============================================================================
// Per-launch state
// =============================================================================

interface LaunchEntry {
  status: LaunchStatus
  process: Subprocess | null
  output: string[]
  containerCheckInterval: ReturnType<typeof setInterval> | null
}

/** Maximum number of log lines to keep per launch */
const MAX_LAUNCH_OUTPUT_LINES = 5000

// =============================================================================
// State — Map of concurrent launches
// =============================================================================

const launches: Map<string, LaunchEntry> = new Map()

/** WebSocket clients subscribed to launch updates */
let launchSubscribers: Set<any> = new Set()

// =============================================================================
// WebSocket broadcast helpers
// =============================================================================

/**
 * Broadcast a status update for a specific launch to all subscribers.
 * Message format: { type: "status", launch_id: string, data: LaunchStatus }
 */
function broadcastStatus(launchId: string): void {
  const entry = launches.get(launchId)
  if (!entry) return

  const message = JSON.stringify({
    type: "status",
    launch_id: launchId,
    data: entry.status,
  })

  for (const ws of launchSubscribers) {
    try {
      ws.send(message)
    } catch (error) {
      console.error("Failed to send status to subscriber:", error)
      launchSubscribers.delete(ws)
    }
  }
}

/**
 * Broadcast a log line for a specific launch to all subscribers.
 * Message format: { type: "log", launch_id: string, data: string }
 */
function broadcastLog(launchId: string, line: string): void {
  const message = JSON.stringify({
    type: "log",
    launch_id: launchId,
    data: line,
  })

  for (const ws of launchSubscribers) {
    try {
      ws.send(message)
    } catch (error) {
      console.error("Failed to send log to subscriber:", error)
      launchSubscribers.delete(ws)
    }
  }
}

/**
 * Broadcast a "cleared" event when a launch is removed.
 * Message format: { type: "cleared", launch_id: string }
 */
function broadcastCleared(launchId: string): void {
  const message = JSON.stringify({
    type: "cleared",
    launch_id: launchId,
  })

  for (const ws of launchSubscribers) {
    try {
      ws.send(message)
    } catch (error) {
      console.error("Failed to send cleared to subscriber:", error)
      launchSubscribers.delete(ws)
    }
  }
}

// =============================================================================
// Container Check (per-launch)
// =============================================================================

function startContainerCheck(launchId: string): void {
  const entry = launches.get(launchId)
  if (!entry || entry.containerCheckInterval) return
  if (entry.status.status !== "launching") return

  console.log(`[launch:${launchId}] Starting container check interval`)

  entry.containerCheckInterval = setInterval(async () => {
    const e = launches.get(launchId)
    if (!e || e.status.status !== "launching") {
      stopContainerCheck(launchId)
      return
    }

    try {
      const containers = await listContainers()
      const match = containers.find((c) => c.taskId === e.status.taskId)
      if (match) {
        console.log(
          `[launch:${launchId}] Container ready: ${match.id} (task: ${e.status.taskId})`
        )
        setLaunchRunning(launchId, match.id)
      }
    } catch (error) {
      console.error(`[launch:${launchId}] Failed to check containers:`, error)
    }
  }, 2000)
}

function stopContainerCheck(launchId: string): void {
  const entry = launches.get(launchId)
  if (!entry?.containerCheckInterval) return

  console.log(`[launch:${launchId}] Stopping container check interval`)
  clearInterval(entry.containerCheckInterval)
  entry.containerCheckInterval = null
}

// =============================================================================
// Data Fetching Functions (unchanged)
// =============================================================================

export function getLocalTasks(): Task[] {
  if (!existsSync(LOCAL_TASKS_PATH)) {
    return []
  }

  try {
    const entries = readdirSync(LOCAL_TASKS_PATH, { withFileTypes: true })
    return entries
      .filter((e) => e.isDirectory() || e.isSymbolicLink())
      .filter((e) => !e.name.startsWith(".") && e.name !== "generate.sh")
      .map((e) => ({ id: e.name }))
  } catch (error) {
    console.error("Failed to read local tasks:", error)
    return []
  }
}

export function isCatalogConfigured(): boolean {
  return CATALOG_URL !== null
}

export async function getRemoteTasks(): Promise<Task[]> {
  if (!CATALOG_URL) {
    throw new Error(CATALOG_NOT_CONFIGURED)
  }

  try {
    const response = await fetch(`${CATALOG_URL}/tasks`, {
      signal: AbortSignal.timeout(10000),
    })

    if (!response.ok) {
      throw new Error(`API returned ${response.status}`)
    }

    const data = await response.json()

    if (Array.isArray(data)) {
      return data.map(
        (t: { id: string; language?: string; project?: string }) => ({
          id: t.id,
          language: t.language,
          project: t.project,
        })
      )
    }

    return []
  } catch (error) {
    console.error("Failed to fetch remote tasks:", error)
    throw error
  }
}

export function getModels(): string[] {
  if (!existsSync(MODELS_PATH)) {
    return []
  }

  try {
    const files = readdirSync(MODELS_PATH).filter(
      (f) => f.endsWith(".yaml") || f.endsWith(".yml")
    )
    const models: string[] = []

    for (const file of files) {
      const content = readFileSync(join(MODELS_PATH, file), "utf-8")
      const matches = content.matchAll(/model_name:\s*(.+)/g)
      for (const match of matches) {
        const modelName = match[1].trim()
        if (modelName && !models.includes(modelName)) {
          models.push(modelName)
        }
      }
    }

    return models.sort()
  } catch (error) {
    console.error("Failed to read models:", error)
    return []
  }
}

export function getAgents(): string[] {
  if (!existsSync(AGENTS_PATH)) {
    return []
  }

  try {
    const entries = readdirSync(AGENTS_PATH, { withFileTypes: true })
    return entries
      .filter((e) => e.isDirectory())
      .filter((e) => !e.name.startsWith("."))
      .map((e) => e.name)
      .sort()
  } catch (error) {
    console.error("Failed to read agents:", error)
    return []
  }
}

export function hasLocalBenchmarks(): boolean {
  return getLocalTasks().length > 0
}

// =============================================================================
// Launch Request Validation
// =============================================================================

const TASK_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/
const MAX_TIMEOUT_SECONDS = 7 * 24 * 60 * 60
const MAX_DIFFICULTY = 4

export type LaunchValidation =
  | { ok: true; config: LaunchConfig }
  | { ok: false; error: string }

/**
 * Validate a launch request body. Models, agents and local tasks must be
 * ones this server lists; remote task IDs must be plain identifiers.
 */
export function validateLaunchConfig(input: unknown): LaunchValidation {
  const fail = (error: string): LaunchValidation => ({ ok: false, error })

  if (typeof input !== "object" || input === null) {
    return fail("Invalid launch request")
  }
  const { task, model, agent, mode, source, timeout, difficulty } =
    input as Record<string, unknown>

  if (!task || !model || !agent || !mode || !source) {
    return fail("Missing required fields")
  }
  if (source !== "local" && source !== "remote") {
    return fail("Invalid source: expected local or remote")
  }
  if (mode !== "sandbox" && mode !== "sidecar") {
    return fail("Invalid mode: expected sandbox or sidecar")
  }
  if (typeof model !== "string" || !getModels().includes(model)) {
    return fail("Unknown model")
  }
  if (typeof agent !== "string" || !getAgents().includes(agent)) {
    return fail("Unknown agent")
  }
  if (typeof task !== "string" || !TASK_ID_PATTERN.test(task)) {
    return fail("Invalid task ID")
  }
  if (source === "local" && !getLocalTasks().some((t) => t.id === task)) {
    return fail("Unknown local task")
  }
  if (source === "remote" && !isCatalogConfigured()) {
    return fail(CATALOG_NOT_CONFIGURED)
  }

  const config: LaunchConfig = { task, model, agent, mode, source }
  if (timeout !== undefined && timeout !== null) {
    if (
      typeof timeout !== "number" ||
      !Number.isInteger(timeout) ||
      timeout <= 0 ||
      timeout > MAX_TIMEOUT_SECONDS
    ) {
      return fail(
        `Invalid timeout: expected whole seconds from 1 to ${MAX_TIMEOUT_SECONDS}`
      )
    }
    config.timeout = timeout
  }
  if (difficulty !== undefined && difficulty !== null) {
    if (
      typeof difficulty !== "number" ||
      !Number.isInteger(difficulty) ||
      difficulty < 0 ||
      difficulty > MAX_DIFFICULTY
    ) {
      return fail(`Invalid difficulty: expected 0 to ${MAX_DIFFICULTY}`)
    }
    config.difficulty = difficulty
  }
  return { ok: true, config }
}

/**
 * Arguments for `uv` that run one benchmark. Values are attached with `=`
 * so none can be read as an option of its own.
 */
export function buildLaunchArgs(config: LaunchConfig): string[] {
  const args = [
    "run",
    "ssebench",
    "run",
    `--model=${config.model}`,
    `--agent=${config.agent}`,
    `--task=${config.task}`,
    `--mode=${config.mode}`,
    "--keep-container",
  ]

  if (config.source === "local") {
    args.push(`--local=${LOCAL_TASKS_PATH}`)
  }

  if (config.timeout !== undefined) {
    args.push(`--timeout=${config.timeout}`)
  }

  if (config.difficulty !== undefined) {
    args.push(`--difficulty=${config.difficulty}`)
  }

  return args
}

// =============================================================================
// Launch State Accessors
// =============================================================================

/** Get status of a specific launch */
export function getLaunchStatus(launchId: string): LaunchStatus | null {
  return launches.get(launchId)?.status ?? null
}

/** Get all active launch statuses */
export function getAllLaunchStatuses(): LaunchStatus[] {
  return Array.from(launches.values()).map((e) => e.status)
}

/** Get logs for a specific launch */
export function getLaunchOutput(launchId: string): string[] {
  return launches.get(launchId)?.output ?? []
}

// =============================================================================
// Launch State Mutations
// =============================================================================

/** Update a launch status to "running" with a container ID (once only) */
function setLaunchRunning(launchId: string, containerId: string): void {
  const entry = launches.get(launchId)
  if (!entry) return

  // Only transition from "launching" → "running" once.
  // Guards against concurrent containerCheckInterval ticks.
  if (entry.status.status !== "launching") return

  entry.status.status = "running"
  entry.status.containerId = containerId
  stopContainerCheck(launchId)
  broadcastStatus(launchId)
}

/** Cancel a specific launch */
export function cancelLaunch(launchId: string): boolean {
  const entry = launches.get(launchId)
  if (!entry || entry.status.status !== "launching") return false

  if (entry.process) {
    entry.process.kill()
    entry.process = null
  }

  entry.status.status = "failed"
  entry.status.error = "Cancelled by user"
  stopContainerCheck(launchId)
  broadcastStatus(launchId)
  return true
}

/** Clear a specific launch entry */
export function clearLaunchEntry(launchId: string): void {
  const entry = launches.get(launchId)
  if (!entry) return

  stopContainerCheck(launchId)

  // Kill process if still running
  if (entry.process) {
    try {
      entry.process.kill()
    } catch {
      // already exited
    }
    entry.process = null
  }

  launches.delete(launchId)
  broadcastCleared(launchId)
}

/** Clear all launch entries */
export function clearAllLaunches(): void {
  for (const [launchId] of launches) {
    clearLaunchEntry(launchId)
  }
}

// =============================================================================
// WebSocket Subscription
// =============================================================================

/** Subscribe a WebSocket client to launch updates */
export function subscribeToLaunch(ws: any): void {
  launchSubscribers.add(ws)

  // Send current state for all active launches
  for (const [launchId, entry] of launches) {
    try {
      // Send status
      ws.send(
        JSON.stringify({
          type: "status",
          launch_id: launchId,
          data: entry.status,
        })
      )

      // Send existing logs
      for (const log of entry.output) {
        ws.send(
          JSON.stringify({
            type: "log",
            launch_id: launchId,
            data: log,
          })
        )
      }
    } catch (error) {
      console.error("Failed to send initial state to subscriber:", error)
    }
  }

  // Start container check for any active launches
  for (const [launchId, entry] of launches) {
    if (entry.status.status === "launching") {
      startContainerCheck(launchId)
    }
  }
}

/** Unsubscribe a WebSocket client */
export function unsubscribeFromLaunch(ws: any): void {
  launchSubscribers.delete(ws)
}

// =============================================================================
// Launch a Task
// =============================================================================

/**
 * Launch a new benchmark task. Returns immediately with the LaunchStatus.
 * `config` must come from validateLaunchConfig.
 */
export async function launchTask(config: LaunchConfig): Promise<LaunchStatus> {
  const args = buildLaunchArgs(config)
  // For display only; the process is spawned from the argument vector
  const command = `uv ${args.join(" ")}`
  const launch_id = crypto.randomUUID()

  // Initialize launch entry
  const status: LaunchStatus = {
    launch_id,
    status: "launching",
    command,
    taskId: config.task,
    startTime: new Date().toISOString(),
  }

  const entry: LaunchEntry = {
    status,
    process: null,
    output: [],
    containerCheckInterval: null,
  }

  launches.set(launch_id, entry)
  broadcastStatus(launch_id)

  // Start container check if there are subscribers
  if (launchSubscribers.size > 0) {
    startContainerCheck(launch_id)
  }

  console.log(`[launch:${launch_id}] Starting: ${command}`)
  console.log(`[launch:${launch_id}] Working directory: ${SSEBENCH_PATH}`)

  try {
    const proc = spawn({
      cmd: ["uv", ...args],
      cwd: SSEBENCH_PATH,
      stdout: "pipe",
      stderr: "pipe",
      env: {
        ...process.env,
        NO_COLOR: "1",
        FORCE_COLOR: "0",
      },
    })

    entry.process = proc

    // Helper to add and broadcast a log line
    const addLog = (line: string) => {
      entry.output.push(line)
      if (entry.output.length > MAX_LAUNCH_OUTPUT_LINES) {
        entry.output.shift()
      }
      broadcastLog(launch_id, line)
    }

    // Stream stdout
    const stdout = proc.stdout
    if (stdout && typeof stdout !== "number") {
      const reader = stdout.getReader()
      ;(async () => {
        try {
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            const text = new TextDecoder().decode(value)
            const lines = text.split("\n").filter((l) => l.trim())
            for (const line of lines) {
              console.log(`[launch:${launch_id}:stdout] ${line}`)
              addLog(line)
            }
          }
        } catch {
          // Stream closed
        }
      })()
    }

    // Stream stderr
    const stderr = proc.stderr
    if (stderr && typeof stderr !== "number") {
      const reader = stderr.getReader()
      ;(async () => {
        try {
          while (true) {
            const { done, value } = await reader.read()
            if (done) break
            const text = new TextDecoder().decode(value)
            const lines = text.split("\n").filter((l) => l.trim())
            for (const line of lines) {
              console.log(`[launch:${launch_id}:stderr] ${line}`)
              addLog(line)
            }
          }
        } catch {
          // Stream closed
        }
      })()
    }

    // Monitor process exit
    proc.exited.then((exitCode) => {
      console.log(`[launch:${launch_id}] Process exited with code: ${exitCode}`)

      const e = launches.get(launch_id)
      if (e && e.status.status === "launching" && exitCode !== 0) {
        e.status.status = "failed"
        e.status.error = `Process exited with code ${exitCode}`
        broadcastStatus(launch_id)
      }

      if (e) {
        e.process = null
      }
    })

    return status
  } catch (error) {
    entry.status.status = "failed"
    entry.status.error = error instanceof Error ? error.message : String(error)
    broadcastStatus(launch_id)
    throw error
  }
}
