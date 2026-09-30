/**
 * Docker CLI wrapper - queries the Docker daemon for SSEBench containers
 *
 * Every call passes an argument vector to the docker binary; nothing goes
 * through a shell. Operations on a single container accept only container
 * IDs and only act on containers carrying the SSEBench label, so request
 * data can neither inject commands nor reach unrelated containers.
 */

import { execFile } from "node:child_process"
import { promisify } from "node:util"
import type { DockerContainer, DockerPsJson } from "../src/types/container"

const execFileAsync = promisify(execFile)

async function docker(args: string[]): Promise<string> {
  const { stdout } = await execFileAsync("docker", args, {
    maxBuffer: 64 * 1024 * 1024,
  })
  return stdout
}

const CONTAINER_ID_PATTERN = /^[a-f0-9]{12,64}$/

/** Short or full hexadecimal container ID, as listed by `docker ps`. */
export function isContainerId(value: unknown): value is string {
  return typeof value === "string" && CONTAINER_ID_PATTERN.test(value)
}

/**
 * Labels used to identify and describe SSEBench containers
 */
const SSEBENCH_LABEL = "ssebench.webui"
const TASK_ID_LABEL = "ssebench.task-id"
const MODEL_LABEL = "ssebench.model"
const AGENT_LABEL = "ssebench.agent"
const REFERENCE_RUN_LABEL = "ssebench.reference-run"
const RUN_ID_LABEL = "ssebench.run-id"

/**
 * Parse Docker status string to normalized status
 */
function parseStatus(status: string): DockerContainer["status"] {
  const lower = status.toLowerCase()
  if (lower.includes("up")) return "running"
  if (lower.includes("exited")) return "exited"
  if (lower.includes("paused")) return "paused"
  if (lower.includes("created")) return "created"
  return "running" // default
}

/**
 * Parse Docker ports string (e.g., "0.0.0.0:8080->80/tcp, :::8080->80/tcp")
 */
function parsePorts(portsStr: string): DockerContainer["ports"] {
  if (!portsStr) return []

  const ports: DockerContainer["ports"] = []
  const portMappings = portsStr.split(", ")

  for (const mapping of portMappings) {
    // Match pattern like "0.0.0.0:8080->80/tcp" or ":::8080->80/tcp"
    const match = mapping.match(
      /(?:\d+\.\d+\.\d+\.\d+|::):(\d+)->(\d+)\/(tcp|udp)/
    )
    if (match) {
      ports.push({
        host: parseInt(match[1], 10),
        container: parseInt(match[2], 10),
        protocol: match[3] as "tcp" | "udp",
      })
    }
  }

  // Dedupe ports (IPv4 and IPv6 create duplicates)
  const seen = new Set<string>()
  return ports.filter((p) => {
    const key = `${p.host}:${p.container}/${p.protocol}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

/**
 * Parse Docker labels string (e.g., "key1=value1,key2=value2")
 */
function parseLabels(labelsStr: string): Record<string, string> {
  if (!labelsStr) return {}

  const labels: Record<string, string> = {}
  // Labels can contain commas in values, so we need careful parsing
  // Docker format: key=value,key2=value2
  const parts = labelsStr.split(",")

  for (const part of parts) {
    const eqIndex = part.indexOf("=")
    if (eqIndex > 0) {
      const key = part.slice(0, eqIndex)
      const value = part.slice(eqIndex + 1)
      labels[key] = value
    }
  }

  return labels
}

/**
 * Transform raw Docker JSON to our container type
 */
function transformContainer(raw: DockerPsJson): DockerContainer {
  const labels = parseLabels(raw.Labels)

  return {
    // Short form, matching `docker ps` without --no-trunc
    id: raw.ID.slice(0, 12),
    name: raw.Names,
    taskId: labels[TASK_ID_LABEL] || "unknown",
    model: labels[MODEL_LABEL] || "unknown",
    agent: labels[AGENT_LABEL] || "unknown",
    referenceRun: labels[REFERENCE_RUN_LABEL] === "true",
    runId: labels[RUN_ID_LABEL] ?? null,
    status: parseStatus(raw.Status),
    image: raw.Image,
    ports: parsePorts(raw.Ports),
    createdAt: raw.CreatedAt,
  }
}

/** Parse `docker ps --format json` output: one JSON object per line */
function parsePsLines(stdout: string): DockerPsJson[] {
  const rows: DockerPsJson[] = []
  for (const line of stdout.split("\n")) {
    if (!line.trim()) continue
    try {
      rows.push(JSON.parse(line))
    } catch {
      console.error("Failed to parse Docker JSON line:", line)
    }
  }
  return rows
}

/**
 * List all SSEBench containers (filtered by label)
 */
export async function listContainers(): Promise<DockerContainer[]> {
  try {
    const stdout = await docker([
      "ps",
      "-a",
      "--filter",
      `label=${SSEBENCH_LABEL}`,
      "--format",
      "json",
    ])
    return parsePsLines(stdout).map(transformContainer)
  } catch (error) {
    console.error("Failed to list containers:", error)
    throw new Error("Failed to query Docker daemon")
  }
}

/**
 * Get a single SSEBench container by ID
 */
export async function getContainer(
  id: string
): Promise<DockerContainer | null> {
  if (!isContainerId(id)) return null
  try {
    // The id filter is an unanchored pattern match, so keep only rows whose
    // full ID starts with the requested one.
    const stdout = await docker([
      "ps",
      "-a",
      "--no-trunc",
      "--filter",
      `id=${id}`,
      "--filter",
      `label=${SSEBENCH_LABEL}`,
      "--format",
      "json",
    ])
    const matches = parsePsLines(stdout).filter((raw) => raw.ID.startsWith(id))
    return matches.length === 1 ? transformContainer(matches[0]) : null
  } catch {
    return null
  }
}

/** Result of resolving a request-supplied ID to an SSEBench container */
export interface ResolvedContainer {
  /** Full 64-character ID; never ambiguous with a container name */
  id: string
  /** Docker state, e.g. "running" or "exited" */
  status: string
  /** First IP address on any attached network */
  ip: string | null
  /** The container's labels */
  labels: Record<string, string>
}

interface DockerInspect {
  Id: string
  State?: { Status?: string }
  Config?: { Labels?: Record<string, string> | null; Env?: string[] | null }
  NetworkSettings?: { Networks?: Record<string, { IPAddress?: string }> }
}

/**
 * What a request-supplied ID names: an SSEBench container, no container at
 * all (never created, or already removed), or something the web UI must not
 * touch (a container without the SSEBench label, or a name that is not an ID).
 */
type Lookup =
  | {
      kind: "ours"
      container: ResolvedContainer
      /** The environment the container was created with */
      env: Record<string, string>
    }
  | { kind: "missing" }
  | { kind: "refused" }

async function lookupContainer(id: string): Promise<Lookup> {
  if (!isContainerId(id)) return { kind: "refused" }
  let info: DockerInspect | undefined
  try {
    const stdout = await docker(["inspect", "--type", "container", id])
    info = (JSON.parse(stdout) as DockerInspect[])[0]
  } catch {
    return { kind: "missing" }
  }
  // docker resolves names before ID prefixes; insist on an ID match.
  if (!info || !info.Id.startsWith(id)) return { kind: "refused" }
  if (info.Config?.Labels?.[SSEBENCH_LABEL] === undefined) {
    return { kind: "refused" }
  }

  const ip =
    Object.values(info.NetworkSettings?.Networks ?? {})
      .map((n) => n.IPAddress)
      .find((addr) => !!addr) ?? null

  const env: Record<string, string> = {}
  for (const entry of info.Config?.Env ?? []) {
    const eq = entry.indexOf("=")
    if (eq > 0) env[entry.slice(0, eq)] = entry.slice(eq + 1)
  }

  return {
    kind: "ours",
    env,
    container: {
      id: info.Id,
      status: info.State?.Status ?? "unknown",
      ip,
      labels: info.Config?.Labels ?? {},
    },
  }
}

/**
 * Resolve an ID to an SSEBench container. Returns null for malformed IDs,
 * unknown containers and containers without the SSEBench label.
 */
export async function resolveContainer(
  id: string
): Promise<ResolvedContainer | null> {
  const found = await lookupContainer(id)
  return found.kind === "ours" ? found.container : null
}

/**
 * The environment a container was created with (`SSE_BASE_URL` and the like),
 * or null when it is not an SSEBench container.
 */
export async function containerEnv(
  id: string
): Promise<Record<string, string> | null> {
  const found = await lookupContainer(id)
  return found.kind === "ours" ? found.env : null
}

/**
 * Check if Docker daemon is accessible
 */
export async function checkDockerAccess(): Promise<boolean> {
  try {
    await docker(["info"])
    return true
  } catch {
    return false
  }
}

/**
 * Outcome of stopping or removing a container. Both operations are idempotent:
 * `ok` means the container is in the requested state afterwards, however it got
 * there, so repeating a request or racing another one is harmless.
 */
export type ContainerOp = "ok" | "refused" | "failed"

const RUNNING_STATES = new Set(["running", "paused", "restarting"])

/**
 * Stop a container by ID: kill it if it is running and leave it on the list as
 * exited. A container that is not running, or is gone, is already stopped.
 */
export async function stopContainer(id: string): Promise<ContainerOp> {
  const found = await lookupContainer(id)
  if (found.kind === "refused") return "refused"
  if (found.kind === "missing") return "ok"
  if (!RUNNING_STATES.has(found.container.status)) return "ok"
  try {
    await docker(["kill", found.container.id])
    return "ok"
  } catch (error) {
    // It may have exited between the inspect and the kill
    const after = await lookupContainer(id)
    if (after.kind === "missing") return "ok"
    if (after.kind === "ours" && !RUNNING_STATES.has(after.container.status)) {
      return "ok"
    }
    console.error(`Failed to kill container ${id}:`, error)
    return "failed"
  }
}

/**
 * Remove a container by ID, running or not. A container that is gone is
 * already removed.
 */
export async function removeContainer(id: string): Promise<ContainerOp> {
  const found = await lookupContainer(id)
  if (found.kind === "refused") return "refused"
  if (found.kind === "missing") return "ok"
  try {
    await docker(["rm", "--force", found.container.id])
    return "ok"
  } catch (error) {
    if ((await lookupContainer(id)).kind === "missing") return "ok"
    console.error(`Failed to remove container ${id}:`, error)
    return "failed"
  }
}

// =============================================================================
// SDK Access Functions - For communicating with SDK daemon inside containers
// =============================================================================

/** Default port that SDK daemon listens on for HTTP (WebUI) connections */
const SDK_HTTP_PORT = 4263

/**
 * Get SDK HTTP URL for a container
 *
 * SDK daemon runs on port 4263 inside containers, reached through the
 * container's IP on its Docker network (no host port mapping needed).
 * Returns the full URL to use for SDK API requests.
 */
export async function getSDKUrl(containerId: string): Promise<string | null> {
  const container = await resolveContainer(containerId)
  if (!container) {
    console.error(`No SSEBench container with ID ${containerId}`)
    return null
  }
  if (!container.ip) {
    console.error(`Container ${containerId} has no IP address`)
    return null
  }

  return `http://${container.ip}:${SDK_HTTP_PORT}`
}

/**
 * Check if SDK daemon is reachable at the given URL
 *
 * Performs a health check by calling the /version endpoint.
 * Returns true if SDK responds successfully within 2 seconds.
 */
export async function checkSDKHealth(sdkUrl: string): Promise<boolean> {
  try {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 2000) // 2s timeout

    const response = await fetch(`${sdkUrl}/version`, {
      signal: controller.signal,
    })

    clearTimeout(timeoutId)
    return response.ok
  } catch (error) {
    // AbortError means timeout, other errors mean connection failed
    console.error(`SDK health check failed for ${sdkUrl}:`, error)
    return false
  }
}
