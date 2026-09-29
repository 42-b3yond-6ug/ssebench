/**
 * API configuration and utilities
 *
 * The API is always same-origin: the production server serves the front end
 * itself, and the Vite dev and preview servers proxy /api to the backend.
 */

import { getAuthToken, notifyAuthRequired, webSocketProtocols } from "./auth"

/**
 * Fetch wrapper that adds the access token, if any
 */
export async function apiFetch(
  path: string,
  options?: RequestInit
): Promise<Response> {
  const headers = new Headers(options?.headers)
  const token = getAuthToken()
  if (token) {
    headers.set("Authorization", `Bearer ${token}`)
  }
  const response = await fetch(path, { ...options, headers })
  if (response.status === 401) {
    notifyAuthRequired()
  }
  return response
}

/**
 * Open a WebSocket to an API path on the current origin
 *
 * Uses ws:// for http:// and wss:// for https://
 */
export function openWebSocket(path: string): WebSocket {
  const { protocol, host } = window.location
  const wsProtocol = protocol === "https:" ? "wss:" : "ws:"
  return new WebSocket(`${wsProtocol}//${host}${path}`, webSocketProtocols())
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
 * Fetch the reference patch from the SDK. The daemon withholds it until the
 * agent phase ends, so it is only available for a finished run.
 */
export async function fetchReferencePatch(
  containerId: string
): Promise<DiffResponse> {
  const response = await apiFetch(
    `/api/containers/${containerId}/reference/patch`
  )
  if (!response.ok) {
    throw new Error(`Failed to fetch reference patch: ${response.status}`)
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
