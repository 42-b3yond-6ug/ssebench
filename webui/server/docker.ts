/**
 * Docker API wrapper - queries Docker daemon for SSEBench containers
 */

import { exec } from "node:child_process"
import { promisify } from "node:util"
import type { DockerContainer, DockerPsJson } from "../src/types/container"

const execAsync = promisify(exec)

/**
 * Labels used to identify and describe SSEBench containers
 */
const SSEBENCH_LABEL = "ssebench.webui"
const TASK_ID_LABEL = "ssebench.task-id"
const MODEL_LABEL = "ssebench.model"
const AGENT_LABEL = "ssebench.agent"

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
    id: raw.ID,
    name: raw.Names,
    taskId: labels[TASK_ID_LABEL] || "unknown",
    model: labels[MODEL_LABEL] || "unknown",
    agent: labels[AGENT_LABEL] || "unknown",
    status: parseStatus(raw.Status),
    image: raw.Image,
    ports: parsePorts(raw.Ports),
    createdAt: raw.CreatedAt,
  }
}

/**
 * List all SSEBench containers (filtered by label)
 */
export async function listContainers(): Promise<DockerContainer[]> {
  try {
    // Query Docker for containers with our label
    const { stdout } = await execAsync(
      `docker ps -a --filter "label=${SSEBENCH_LABEL}" --format json`
    )

    if (!stdout.trim()) {
      return []
    }

    // Docker outputs one JSON object per line
    const lines = stdout.trim().split("\n")
    const containers: DockerContainer[] = []

    for (const line of lines) {
      if (!line.trim()) continue
      try {
        const raw: DockerPsJson = JSON.parse(line)
        containers.push(transformContainer(raw))
      } catch {
        console.error("Failed to parse Docker JSON line:", line)
      }
    }

    return containers
  } catch (error) {
    console.error("Failed to list containers:", error)
    throw new Error("Failed to query Docker daemon")
  }
}

/**
 * Get a single container by ID
 */
export async function getContainer(
  id: string
): Promise<DockerContainer | null> {
  try {
    const { stdout } = await execAsync(
      `docker ps -a --filter "id=${id}" --filter "label=${SSEBENCH_LABEL}" --format json`
    )

    if (!stdout.trim()) {
      return null
    }

    const raw: DockerPsJson = JSON.parse(stdout.trim().split("\n")[0])
    return transformContainer(raw)
  } catch {
    return null
  }
}

/**
 * Check if Docker daemon is accessible
 */
export async function checkDockerAccess(): Promise<boolean> {
  try {
    await execAsync("docker info")
    return true
  } catch {
    return false
  }
}

/**
 * Stop a container by ID - kills immediately and removes
 * @param id Container ID
 * @returns true if killed and removed successfully
 */
export async function stopContainer(id: string): Promise<boolean> {
  try {
    await execAsync(`docker kill ${id}`)
    await execAsync(`docker rm ${id}`)
    return true
  } catch (error) {
    console.error(`Failed to kill/remove container ${id}:`, error)
    return false
  }
}

/**
 * Remove a stopped container by ID
 * @param id Container ID
 * @returns true if removed successfully
 */
export async function removeContainer(id: string): Promise<boolean> {
  try {
    await execAsync(`docker rm ${id}`)
    return true
  } catch (error) {
    console.error(`Failed to remove container ${id}:`, error)
    return false
  }
}

// =============================================================================
// SDK Access Functions - For communicating with SDK daemon inside containers
// =============================================================================

/** Default port that SDK daemon listens on for HTTP (WebUI) connections */
const SDK_HTTP_PORT = 4263

/**
 * Get container IP address on Docker network
 *
 * Containers on ssebench_net have predictable IPs that the host can access.
 * This avoids the need for random port mapping.
 */
async function getContainerIP(containerId: string): Promise<string | null> {
  try {
    const { stdout } = await execAsync(
      `docker inspect ${containerId} --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'`
    )
    const ip = stdout.trim()

    if (!ip) {
      console.error(`Container ${containerId} has no IP address`)
      return null
    }

    return ip
  } catch (error) {
    console.error(`Failed to get IP for container ${containerId}:`, error)
    return null
  }
}

/**
 * Get SDK HTTP URL for a container
 *
 * SDK daemon runs on port 4263 inside containers, accessible via Docker network.
 * Returns the full URL to use for SDK API requests.
 */
export async function getSDKUrl(containerId: string): Promise<string | null> {
  const ip = await getContainerIP(containerId)
  if (!ip) return null

  return `http://${ip}:${SDK_HTTP_PORT}`
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
