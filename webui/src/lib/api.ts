/**
 * API configuration and utilities
 *
 * Uses window.location to derive the API base URL dynamically.
 * Backend runs on port 3001, frontend on port 5173 (dev) or same origin (prod).
 */

/**
 * Get the API base URL based on current window location
 *
 * In development: http://[current-host]:3001
 * In production: same origin with /api prefix (assuming reverse proxy)
 */
function getApiBaseUrl(): string {
  const { protocol, hostname } = window.location

  // In development, Vite runs on 5173, backend on 3001 on the same host
  if (import.meta.env.DEV) {
    return `${protocol}//${hostname}:3001`
  }

  // In production, assume API is served from same origin
  return ""
}

/**
 * Fetch wrapper with base URL
 */
export async function apiFetch(
  path: string,
  options?: RequestInit
): Promise<Response> {
  const baseUrl = getApiBaseUrl()
  return fetch(`${baseUrl}${path}`, options)
}

/**
 * Get the WebSocket base URL
 *
 * Uses ws:// for http:// and wss:// for https://
 */
export function getWsBaseUrl(): string {
  const { protocol, hostname, port } = window.location
  const wsProtocol = protocol === "https:" ? "wss:" : "ws:"

  // In development, Vite runs on 5173, backend on 3001 on the same host
  if (import.meta.env.DEV) {
    return `${wsProtocol}//${hostname}:3001`
  }

  // In production, use same origin with port if present
  const portSuffix = port ? `:${port}` : ""
  return `${wsProtocol}//${hostname}${portSuffix}`
}

// =============================================================================
// SDK API Functions - Fetch data from SDK daemon via backend proxy
// =============================================================================

import type { DiffResponse } from "../types/container"
import type {
  Task,
  TaskSource,
  LaunchConfig,
  LaunchStatus,
  LaunchConfigInfo,
} from "../types/launch"

/**
 * Fetch ground truth patch from SDK (WebUI only)
 * Note: This endpoint is intentionally NOT available to agent clients
 * to maintain benchmark integrity
 */
export async function fetchGroundTruthPatch(
  containerId: string
): Promise<DiffResponse> {
  const response = await apiFetch(
    `/api/containers/${containerId}/cheating/ground_truth`
  )
  if (!response.ok) {
    throw new Error(`Failed to fetch ground truth: ${response.status}`)
  }
  return response.json()
}

// =============================================================================
// Container Management Functions
// =============================================================================

/**
 * Stop a running container
 * @param containerId Container ID to stop
 * @returns true if stopped successfully
 */
export async function stopContainer(containerId: string): Promise<boolean> {
  const response = await apiFetch(`/api/containers/${containerId}/stop`, {
    method: "POST",
  })
  if (!response.ok) {
    throw new Error(`Failed to stop container: ${response.status}`)
  }
  const data = await response.json()
  return data.stopped
}

/**
 * Remove a stopped container
 * @param containerId Container ID to remove
 * @returns true if removed successfully
 */
export async function removeContainer(containerId: string): Promise<boolean> {
  const response = await apiFetch(`/api/containers/${containerId}/remove`, {
    method: "POST",
  })
  if (!response.ok) {
    throw new Error(`Failed to remove container: ${response.status}`)
  }
  const data = await response.json()
  return data.removed
}

// =============================================================================
// Launch API Functions - Task launcher
// =============================================================================

/**
 * Fetch available tasks from local or remote (task catalog) source
 */
export async function fetchLaunchTasks(source: TaskSource): Promise<Task[]> {
  const response = await apiFetch(`/api/launch/tasks?source=${source}`)
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.error || `Failed to fetch tasks: ${response.status}`)
  }
  const data = await response.json()
  return data.tasks || []
}

/**
 * Fetch available models
 */
export async function fetchLaunchModels(): Promise<string[]> {
  const response = await apiFetch("/api/launch/models")
  if (!response.ok) {
    throw new Error(`Failed to fetch models: ${response.status}`)
  }
  const data = await response.json()
  return data.models || []
}

/**
 * Fetch available agents
 */
export async function fetchLaunchAgents(): Promise<string[]> {
  const response = await apiFetch("/api/launch/agents")
  if (!response.ok) {
    throw new Error(`Failed to fetch agents: ${response.status}`)
  }
  const data = await response.json()
  return data.agents || []
}

/**
 * Fetch launch configuration (which task sources are available)
 */
export async function fetchLaunchConfig(): Promise<LaunchConfigInfo> {
  const response = await apiFetch("/api/launch/config")
  if (!response.ok) {
    throw new Error(`Failed to fetch launch config: ${response.status}`)
  }
  return response.json()
}

/**
 * Launch a new benchmark task
 */
export async function launchTask(config: LaunchConfig): Promise<LaunchStatus> {
  const response = await apiFetch("/api/launch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  })
  if (!response.ok) {
    const data = await response.json()
    throw new Error(data.error || `Launch failed: ${response.status}`)
  }
  return response.json()
}

/**
 * Cancel a specific launch
 */
export async function cancelLaunch(launchId: string): Promise<boolean> {
  const response = await apiFetch("/api/launch/cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ launch_id: launchId }),
  })
  if (!response.ok) {
    throw new Error(`Failed to cancel launch: ${response.status}`)
  }
  const data = await response.json()
  return data.cancelled
}

/**
 * Clear a specific launch entry
 */
export async function clearLaunchEntry(launchId: string): Promise<void> {
  const response = await apiFetch("/api/launch/clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ launch_id: launchId }),
  })
  if (!response.ok) {
    throw new Error(`Failed to clear launch entry: ${response.status}`)
  }
}

/**
 * Clear all launch entries
 */
export async function clearAllLaunches(): Promise<void> {
  const response = await apiFetch("/api/launch/clear", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  })
  if (!response.ok) {
    throw new Error(`Failed to clear launches: ${response.status}`)
  }
}
