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

import { spawn, type ServerWebSocket, type Subprocess } from "bun"
import { readdirSync, readFileSync, existsSync } from "fs"
import { join } from "path"
import { loadCatalogTasks, resolveCatalog, type CatalogTask } from "./catalog"
import { ssebenchPath } from "./config"
import { listRuns, refreshRuns, runnerCommand, runnerEnv } from "./runner"

// =============================================================================
// Configuration
// =============================================================================

// Read once: the paths below do not change while the server runs.
const SSEBENCH_PATH = ssebenchPath()
export const LOCAL_TASKS_PATH =
  process.env.SSEBENCH_LOCAL_TASKS || join(SSEBENCH_PATH, "datasets", "pilot")
const MODELS_PATH = join(SSEBENCH_PATH, "models")
const AGENTS_PATH = join(SSEBENCH_PATH, "agents")
const PLUGINS_FILE = join(SSEBENCH_PATH, "runtime", "plugins", "plugins.yaml")

/** The agent that applies the task's known fix and makes no model calls */
export const REFERENCE_AGENT = "reference"

// Task catalog for the "Catalog" source, handed to the CLI as --catalog so
// that both read the same one.
export const CATALOG = resolveCatalog(
  process.env,
  join(SSEBENCH_PATH, "datasets", "pilot", "manifest.json")
)

export const CATALOG_NOT_CONFIGURED =
  "Task catalog not configured: set SSEBENCH_CATALOG for the webui server"

// =============================================================================
// Types
// =============================================================================

type Task = CatalogTask

export interface LaunchConfig {
  task: string
  /** Absent for the reference agent, which uses none */
  model?: string
  agent: string
  mode: "sandbox" | "sidecar"
  source: "local" | "remote"
  timeout?: number
  difficulty?: number
  egress?: "restricted" | "open"
  /** Plugins to run instead of those plugins.yaml enables; sandbox mode only */
  plugins?: string[]
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
const launchSubscribers: Set<ServerWebSocket<unknown>> = new Set()

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

    await findRunContainer(launchId)
  }, 2000)
}

/**
 * Look for the container of a launch by the run ID it passed to the CLI and
 * mark the launch running when it exists. Task IDs do not identify a run:
 * other launches, other users and other Compose projects share them.
 */
export async function findRunContainer(launchId: string): Promise<boolean> {
  const entry = launches.get(launchId)
  if (!entry || entry.status.status !== "launching") return false
  try {
    // The list is shared for a moment, and a run that has just started may
    // not be in it yet
    refreshRuns()
    const { runs } = await listRuns()
    const match = runs.find((run) => run.run_id === launchId)
    if (!match) return false
    console.log(
      `[launch:${launchId}] Container ready: ${match.name} (task: ${entry.status.taskId})`
    )
    setLaunchRunning(launchId, match.run_id)
    return true
  } catch (error) {
    console.error(`[launch:${launchId}] Failed to check containers:`, error)
    return false
  }
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
  return CATALOG !== null
}

export async function getRemoteTasks(): Promise<Task[]> {
  if (!CATALOG) {
    throw new Error(CATALOG_NOT_CONFIGURED)
  }

  try {
    return await loadCatalogTasks(CATALOG.location)
  } catch (error) {
    console.error("Failed to read the task catalog:", error)
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

export interface PluginInfo {
  name: string
  /** plugins.yaml runs it in every run */
  enabled: boolean
  hook: string
  /** It gets the run's LiteLLM endpoint, key and model */
  llm: boolean
}

/**
 * The plugins that runtime/plugins/plugins.yaml declares, in file order. The
 * file is a flat list of `- name:` entries, and `ssebench run` validates it.
 */
export function getPlugins(): PluginInfo[] {
  if (!existsSync(PLUGINS_FILE)) return []
  try {
    const plugins: PluginInfo[] = []
    for (const line of readFileSync(PLUGINS_FILE, "utf-8").split("\n")) {
      const name = line.match(/^-\s+name:\s*([A-Za-z0-9._-]+)\s*$/)
      if (name) {
        plugins.push({ name: name[1], enabled: false, hook: "", llm: false })
        continue
      }
      const field = line.match(/^\s+(enabled|hook|llm):\s*([A-Za-z0-9-]+)\s*$/)
      const current = plugins[plugins.length - 1]
      if (!field || !current) continue
      if (field[1] === "hook") current.hook = field[2]
      else current[field[1] as "enabled" | "llm"] = field[2] === "true"
    }
    return plugins
  } catch (error) {
    console.error("Failed to read plugins:", error)
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
  const { task, model, agent, mode, source, timeout, difficulty, egress } =
    input as Record<string, unknown>
  const plugins = (input as Record<string, unknown>).plugins

  if (!task || !agent || !mode || !source) {
    return fail("Missing required fields")
  }
  if (source !== "local" && source !== "remote") {
    return fail("Invalid source: expected local or remote")
  }
  if (mode !== "sandbox" && mode !== "sidecar") {
    return fail("Invalid mode: expected sandbox or sidecar")
  }
  if (typeof agent !== "string" || !getAgents().includes(agent)) {
    return fail("Unknown agent")
  }
  // The reference agent makes no model calls; any model sent is ignored.
  const needsModel = agent !== REFERENCE_AGENT
  if (needsModel) {
    if (!model) return fail("Missing required fields")
    if (typeof model !== "string" || !getModels().includes(model)) {
      return fail("Unknown model")
    }
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

  const config: LaunchConfig = { task, agent, mode, source }
  if (needsModel) config.model = model as string
  if (egress !== undefined && egress !== null) {
    if (egress !== "restricted" && egress !== "open") {
      return fail("Invalid egress: expected restricted or open")
    }
    config.egress = egress
  }
  if (plugins !== undefined && plugins !== null) {
    if (
      !Array.isArray(plugins) ||
      !plugins.every((name) => typeof name === "string")
    ) {
      return fail("Invalid plugins: expected a list of plugin names")
    }
    const known = getPlugins().map((p) => p.name)
    if (!plugins.every((name) => known.includes(name))) {
      return fail("Unknown plugin")
    }
    if (plugins.length > 0 && mode !== "sandbox") {
      return fail("Plugins apply to sandbox mode only")
    }
    if (plugins.length > 0) config.plugins = [...new Set(plugins)]
  }
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
 * Arguments for `ssebench` that run one benchmark. Values are attached with
 * `=` so none can be read as an option of its own. `runId` labels the run's
 * containers, so the launch can tell them from every other container.
 */
export function buildLaunchArgs(config: LaunchConfig, runId: string): string[] {
  const args = ["run"]
  if (config.model !== undefined) args.push(`--model=${config.model}`)
  args.push(
    `--agent=${config.agent}`,
    `--task=${config.task}`,
    `--mode=${config.mode}`,
    `--run-id=${runId}`,
    "--keep-container"
  )

  if (config.source === "local") {
    args.push(`--local=${LOCAL_TASKS_PATH}`)
  } else if (CATALOG) {
    args.push(`--catalog=${CATALOG.location}`)
  }

  if (config.timeout !== undefined) {
    args.push(`--timeout=${config.timeout}`)
  }

  if (config.difficulty !== undefined) {
    args.push(`--difficulty=${config.difficulty}`)
  }

  if (config.egress !== undefined) {
    args.push(`--egress=${config.egress}`)
  }

  for (const plugin of config.plugins ?? []) {
    args.push(`--plugin=${plugin}`)
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

/**
 * Clear a specific launch entry. Clearing a launch that has not reached its
 * container stops it. Once the container exists the run belongs to the
 * container, not to this entry: the CLI keeps running until the container
 * stops, and then writes the run's summary and spend, so it is detached
 * rather than killed.
 */
export function clearLaunchEntry(launchId: string): void {
  const entry = launches.get(launchId)
  if (!entry) return

  stopContainerCheck(launchId)

  if (entry.process && entry.status.status === "launching") {
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
export function subscribeToLaunch(ws: ServerWebSocket<unknown>): void {
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
export function unsubscribeFromLaunch(ws: ServerWebSocket<unknown>): void {
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
  const launch_id = crypto.randomUUID()
  // The launch ID is also the run ID that labels the run's containers
  const args = buildLaunchArgs(config, launch_id)
  // For display only; the process is spawned from the argument vector
  const command = [...runnerCommand(), ...args].join(" ")

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
      cmd: [...runnerCommand(), ...args],
      cwd: SSEBENCH_PATH,
      stdout: "pipe",
      stderr: "pipe",
      env: runnerEnv(),
    })

    entry.process = proc

    // Helper to add and broadcast a log line. A detached run keeps writing
    // to its pipes, which are read to the end so it never blocks on them,
    // but its lines belong to no launch any more.
    const addLog = (line: string) => {
      if (launches.get(launch_id) !== entry) return
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
    proc.exited.then(async (exitCode) => {
      console.log(`[launch:${launch_id}] Process exited with code: ${exitCode}`)

      const e = launches.get(launch_id)
      if (e) {
        e.process = null
      }
      if (!e || e.status.status !== "launching") return

      // A run that ended before the periodic check saw its container still
      // has one; only a launch without a container has failed.
      stopContainerCheck(launch_id)
      if (await findRunContainer(launch_id)) return
      if (e.status.status !== "launching") return
      e.status.status = "failed"
      e.status.error =
        exitCode === 0
          ? "The run ended without starting a container"
          : `Process exited with code ${exitCode}`
      broadcastStatus(launch_id)
    })

    return status
  } catch (error) {
    entry.status.status = "failed"
    entry.status.error = error instanceof Error ? error.message : String(error)
    broadcastStatus(launch_id)
    throw error
  }
}
