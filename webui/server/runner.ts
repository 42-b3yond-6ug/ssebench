/**
 * The runner: how the server finds, stops and reaches runs.
 *
 * Everything that depends on where the runs execute goes through the
 * `ssebench runs` commands, which the CLI implements on its backend
 * interface. The server never runs `docker` or `kubectl` itself, so the same
 * build serves any backend. Every call passes an argument vector; nothing
 * goes through a shell. A run is named by its run ID, which is checked
 * against the pattern the CLI enforces before it reaches a command line, so
 * request data can neither inject commands nor reach anything that is not a
 * run.
 *
 * A command is a process of its own, and Python takes a moment to start, so
 * the run list is shared between callers for a short time and the URL of a
 * run's port is remembered.
 */

import { ssebenchPath } from "./config"
import type { DockerContainer } from "../src/types/container"

/** The command that runs the CLI, unless SSEBENCH_CLI names another */
const DEFAULT_CLI = ["uv", "run", "ssebench"]

/**
 * The CLI as an argument vector. SSEBENCH_CLI is split on white space, so it
 * can be `ssebench`, or `uv run --project /opt/ssebench ssebench`; it is not
 * parsed by a shell, and quoting has no meaning in it.
 */
export function runnerCommand(env = process.env): string[] {
  const configured = env.SSEBENCH_CLI?.trim()
  return configured ? configured.split(/\s+/) : DEFAULT_CLI
}

/** The environment of a CLI process */
export function runnerEnv(): Record<string, string | undefined> {
  return { ...process.env, NO_COLOR: "1", FORCE_COLOR: "0" }
}

const RUN_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/
/** The source of the pattern, for routes that match an ID inside a path */
export const RUN_ID_SOURCE = "[A-Za-z0-9][A-Za-z0-9_.-]{0,63}"

/**
 * Whether `value` can be a run ID: 1 to 64 letters, digits, `.`, `_` or `-`,
 * starting with a letter or digit, and not `latest`, which names a link
 * beside the run directories.
 */
export function isRunId(value: unknown): value is string {
  return (
    typeof value === "string" &&
    RUN_ID_PATTERN.test(value) &&
    value.toLowerCase() !== "latest"
  )
}

const EXIT_NOT_FOUND = 3
const EXIT_AMBIGUOUS = 4
const TIMEOUT_MS = 60_000

export interface CliResult {
  code: number
  stdout: string
  stderr: string
}

/** Run the CLI with `args` and collect its output. Rejects if it cannot start or times out. */
export async function runCli(
  args: string[],
  options: { timeoutMs?: number; env?: Record<string, string | undefined> } = {}
): Promise<CliResult> {
  const proc = Bun.spawn({
    cmd: [...runnerCommand(), ...args],
    cwd: ssebenchPath(),
    env: options.env ?? runnerEnv(),
    stdin: "ignore",
    stdout: "pipe",
    stderr: "pipe",
  })
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    proc.kill()
  }, options.timeoutMs ?? TIMEOUT_MS)
  try {
    const [stdout, stderr, code] = await Promise.all([
      new Response(proc.stdout).text(),
      new Response(proc.stderr).text(),
      proc.exited,
    ])
    if (timedOut) throw new Error(`\`ssebench ${args[0]}\` timed out`)
    return { code, stdout, stderr }
  } finally {
    clearTimeout(timer)
  }
}

/** The first line of the CLI's complaint, for an error message */
function complaint(result: CliResult): string {
  const lines = result.stderr.trim().split("\n")
  return lines[lines.length - 1] || `exit status ${result.code}`
}

// =============================================================================
// Runs on the backend
// =============================================================================

/** A run as `ssebench runs list --json` reports it */
export interface RunnerRun {
  run_id: string
  name: string
  state: "created" | "running" | "exited" | "unknown"
  exit_code: number | null
  image: string
  created_at: string | null
  task: string | null
  model: string | null
  agent: string | null
  reference_run: boolean
  results_dir: string | null
  labels: Record<string, string>
}

export interface RunnerList {
  /** The name of the backend that the CLI selected */
  backend: string
  /** Whether the backend can run commands in a run: the terminal and the assistant need it */
  supports_exec: boolean
  runs: RunnerRun[]
}

const LIST_TTL_MS = 1500

let listing: { at: number; result: Promise<RunnerList> } | null = null

async function fetchList(): Promise<RunnerList> {
  const result = await runCli(["runs", "list", "--json"])
  if (result.code !== 0) {
    throw new Error(`Could not list the runs: ${complaint(result)}`)
  }
  const parsed = JSON.parse(result.stdout) as RunnerList
  if (!Array.isArray(parsed.runs)) {
    throw new Error("`ssebench runs list --json` printed no list of runs")
  }
  return parsed
}

/** The runs on the backend. Callers within a moment share one command. */
export function listRuns(): Promise<RunnerList> {
  if (!listing || Date.now() - listing.at > LIST_TTL_MS) {
    const result = fetchList()
    listing = { at: Date.now(), result }
    // A failure is not worth remembering
    result.catch(() => {
      if (listing?.result === result) listing = null
    })
  }
  return listing.result
}

/** Forget the last listing, so the next one asks the backend */
export function refreshRuns(): void {
  listing = null
}

/** Forget the listing and a run's remembered URLs, after a change to the run */
export function forgetRuns(id: string): void {
  listing = null
  forgetEndpoint(id)
}

const RUN_STATUS: Record<RunnerRun["state"], DockerContainer["status"]> = {
  created: "created",
  running: "running",
  exited: "exited",
  unknown: "unknown",
}

/** A live run as the UI lists it */
export function toContainer(run: RunnerRun): DockerContainer {
  return {
    id: run.run_id,
    name: run.name,
    taskId: run.task || "unknown",
    model: run.model || "unknown",
    agent: run.agent || "unknown",
    referenceRun: run.reference_run,
    runId: run.run_id,
    status: RUN_STATUS[run.state] ?? "unknown",
    image: run.image,
    createdAt: run.created_at ?? "",
    source: "container",
  }
}

/**
 * Whether the runner can list runs at all, and what it can do: the backend's
 * name and whether it runs commands in a run.
 */
export async function checkRunnerAccess(): Promise<
  | { ok: true; backend: string; supportsExec: boolean }
  | { ok: false; error: string }
> {
  try {
    const { backend, supports_exec } = await listRuns()
    return { ok: true, backend, supportsExec: supports_exec }
  } catch (error) {
    return {
      ok: false,
      error: error instanceof Error ? error.message : String(error),
    }
  }
}

/**
 * Outcome of stopping or removing a run. Both operations are idempotent:
 * `ok` means the run is in the requested state afterwards, however it got
 * there, so repeating a request or racing another one is harmless.
 */
export type RunOp = "ok" | "refused" | "ambiguous" | "failed"

async function operate(verb: "stop" | "remove", id: string): Promise<RunOp> {
  if (!isRunId(id)) return "refused"
  try {
    const result = await runCli(["runs", verb, id])
    forgetRuns(id)
    if (result.code === 0 || result.code === EXIT_NOT_FOUND) return "ok"
    if (result.code === EXIT_AMBIGUOUS) return "ambiguous"
    console.error(`Failed to ${verb} run ${id}: ${complaint(result)}`)
    return "failed"
  } catch (error) {
    console.error(`Failed to ${verb} run ${id}:`, error)
    return "failed"
  }
}

/** Stop a run's containers, leaving them in place. A run that is not running, or is gone, is already stopped. */
export function stopRun(id: string): Promise<RunOp> {
  return operate("stop", id)
}

/** Remove a run's containers, running or not. A run that is gone is already removed. */
export function removeRun(id: string): Promise<RunOp> {
  return operate("remove", id)
}

// =============================================================================
// Reaching a running run
// =============================================================================

const ENDPOINT_TTL_MS = 30_000

const endpoints = new Map<string, { at: number; url: string }>()

/**
 * The URL at which the server can reach `port` of a run's container, or null
 * when the run is not running or the backend cannot reach it. It is
 * remembered for a while, since one run is asked for many times.
 */
export async function endpointOf(
  id: string,
  port: number
): Promise<string | null> {
  if (!isRunId(id)) return null
  const key = `${id}:${port}`
  const known = endpoints.get(key)
  if (known && Date.now() - known.at < ENDPOINT_TTL_MS) return known.url
  try {
    const result = await runCli([
      "runs",
      "endpoint",
      "--json",
      id,
      String(port),
    ])
    if (result.code !== 0) {
      endpoints.delete(key)
      return null
    }
    const { url } = JSON.parse(result.stdout) as { url?: unknown }
    if (typeof url !== "string" || !/^https?:\/\//.test(url)) return null
    endpoints.set(key, { at: Date.now(), url })
    return url
  } catch (error) {
    console.error(`Could not reach port ${port} of run ${id}:`, error)
    return null
  }
}

/** Forget a run's remembered URLs, after a request to it failed to connect */
export function forgetEndpoint(id: string): void {
  for (const key of [...endpoints.keys()]) {
    if (key.startsWith(`${id}:`)) endpoints.delete(key)
  }
}

/** Port of the SSEBench daemon in a run's container */
const SDK_HTTP_PORT = 4263

/** The daemon's URL for a run, or null while it cannot be reached */
export function getSDKUrl(id: string): Promise<string | null> {
  return endpointOf(id, SDK_HTTP_PORT)
}

/**
 * Check if the daemon is reachable at the given URL, by asking for its
 * version. True if it answers within 2 seconds.
 */
export async function checkSDKHealth(sdkUrl: string): Promise<boolean> {
  try {
    const response = await fetch(`${sdkUrl}/version`, {
      signal: AbortSignal.timeout(2000),
    })
    return response.ok
  } catch (error) {
    console.error(`SDK health check failed for ${sdkUrl}:`, error)
    return false
  }
}

// =============================================================================
// Commands in a run
// =============================================================================

/** Options of `ssebench runs exec` that the server uses */
export interface ExecOptions {
  user?: string
  workdir?: string
  tty?: boolean
  stdin?: boolean
  /** Variables the command gets, by name; their values come from the CLI's environment */
  envNames?: string[]
}

/** The argument vector that runs `command` in a run, through the CLI. `command` is never parsed by a shell. */
export function execCommand(
  id: string,
  command: string[],
  options: ExecOptions = {}
): string[] {
  return [
    ...runnerCommand(),
    "runs",
    "exec",
    ...(options.user ? ["--user", options.user] : []),
    ...(options.workdir ? ["--workdir", options.workdir] : []),
    ...(options.tty ? ["--tty"] : []),
    ...(options.stdin ? ["--stdin"] : []),
    ...(options.envNames ?? []).flatMap((name) => ["--env", name]),
    id,
    "--",
    ...command,
  ]
}

const ENV_NAME = /^[A-Z_][A-Z0-9_]*$/

/**
 * Variables of a running container's environment, by name, or null when the
 * run cannot run commands. The values are read by a command in the
 * container, so they are the ones it was started with.
 */
export async function containerEnv(
  id: string,
  names: string[]
): Promise<Record<string, string> | null> {
  if (!isRunId(id) || !names.every((name) => ENV_NAME.test(name))) return null
  try {
    const result = await runCli([
      "runs",
      "exec",
      id,
      "--",
      "sh",
      "-c",
      'for name in "$@"; do printenv "$name" || echo; done',
      "sh",
      ...names,
    ])
    if (result.code !== 0) return null
    const lines = result.stdout.split("\n")
    return Object.fromEntries(names.map((name, i) => [name, lines[i] ?? ""]))
  } catch {
    return null
  }
}
