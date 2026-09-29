/**
 * SDK WebSocket Manager
 *
 * Manages WebSocket connections for SDK data streaming with:
 * - SDK readiness detection with backoff
 * - Adaptive polling (faster when active, slower when idle)
 * - Change detection to minimize broadcasts
 * - Single connection per container serving multiple clients
 */

import type { ServerWebSocket } from "bun"
import { getSDKUrl, checkSDKHealth } from "./docker"
import type {
  ProjectInfo,
  ChangedFile,
  DialogEntry,
  EvaluationResultResponse,
} from "../src/types/container"

// =============================================================================
// Configuration
// =============================================================================

/** Polling intervals for adaptive polling */
const POLL_FAST = 1000 // 1s when active (recent changes)
const POLL_NORMAL = 3000 // 3s default
const POLL_SLOW = 10000 // 10s when idle
const IDLE_THRESHOLD = 60000 // 60s to consider idle

/** SDK readiness check configuration */
const SDK_READY_MAX_WAIT_MS = 25 * 60 * 1000 // 25 minutes max wait time
const SDK_READY_POLL_INTERVAL_MS = 10000 // 10 seconds between checks after initial backoff

/** SDK readiness check backoff delays (ms) - initial quick checks then steady polling */
const READINESS_INITIAL_BACKOFF = [1000, 2000, 5000, 10000] // First 18 seconds: quick checks

// =============================================================================
// Types
// =============================================================================

/** Connection state for a container */
interface SDKConnection {
  containerId: string
  clients: Set<ServerWebSocket<unknown>>
  status: "connecting" | "ready" | "error"
  sdkUrl: string | null
  errorMessage: string | null

  // Cached data (for change detection)
  project: ProjectInfo | null
  files: ChangedFile[]
  diff: string
  dialogLastSeq: number
  dialogEntries: DialogEntry[]
  result: EvaluationResultResponse | null

  // Polling state
  pollTimeout: ReturnType<typeof setTimeout> | null
  lastActivity: number // Timestamp of last data change
  isPolling: boolean
}

/** WebSocket message types sent to clients */
type SDKWebSocketMessage =
  | { type: "status"; status: "connecting"; retryAttempt?: number }
  | { type: "status"; status: "ready"; sdkVersion?: string }
  | { type: "status"; status: "error"; error: string }
  | { type: "project"; data: ProjectInfo }
  | { type: "files"; files: ChangedFile[] }
  | { type: "diff"; diff: string }
  | { type: "dialog"; entries: DialogEntry[]; lastSeq: number }
  | { type: "result"; result: EvaluationResultResponse }
  | { type: "error"; error: string }

// =============================================================================
// State
// =============================================================================

/** Active connections by container ID */
const connections = new Map<string, SDKConnection>()

// =============================================================================
// Utility Functions
// =============================================================================

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function broadcastToClients(
  conn: SDKConnection,
  message: SDKWebSocketMessage
): void {
  const json = JSON.stringify(message)
  for (const client of conn.clients) {
    try {
      client.send(json)
    } catch (error) {
      console.error(
        `[SDK-WS] Failed to send to client for ${conn.containerId}:`,
        error
      )
      conn.clients.delete(client)
    }
  }
}

function getAdaptivePollInterval(conn: SDKConnection): number {
  const idleTime = Date.now() - conn.lastActivity

  if (idleTime < 5000) return POLL_FAST // Very active: 1s
  if (idleTime < IDLE_THRESHOLD) return POLL_NORMAL // Normal: 3s
  return POLL_SLOW // Idle: 10s
}

// =============================================================================
// SDK Readiness Check
// =============================================================================

async function waitForSDKReady(conn: SDKConnection): Promise<boolean> {
  const startTime = Date.now()
  let attempt = 0

  while (Date.now() - startTime < SDK_READY_MAX_WAIT_MS) {
    // Check if any clients still connected
    if (conn.clients.size === 0) {
      console.log(
        `[SDK-WS] No clients remaining for ${conn.containerId}, stopping readiness check`
      )
      return false
    }

    // Try to get SDK URL and check health
    const sdkUrl = await getSDKUrl(conn.containerId)
    if (sdkUrl) {
      const healthy = await checkSDKHealth(sdkUrl)
      if (healthy) {
        conn.sdkUrl = sdkUrl
        conn.status = "ready"
        const elapsed = Math.round((Date.now() - startTime) / 1000)
        console.log(
          `[SDK-WS] SDK ready for ${conn.containerId} at ${sdkUrl} (took ${elapsed}s)`
        )
        return true
      }
    }

    attempt++
    const elapsed = Math.round((Date.now() - startTime) / 1000)
    const remaining = Math.round(
      (SDK_READY_MAX_WAIT_MS - (Date.now() - startTime)) / 1000
    )

    // Broadcast retry status
    broadcastToClients(conn, {
      type: "status",
      status: "connecting",
      retryAttempt: attempt,
    })

    // Calculate delay: use initial backoff array, then steady polling
    const delay =
      attempt <= READINESS_INITIAL_BACKOFF.length
        ? READINESS_INITIAL_BACKOFF[attempt - 1]
        : SDK_READY_POLL_INTERVAL_MS

    console.log(
      `[SDK-WS] SDK not ready for ${conn.containerId}, attempt ${attempt} (${elapsed}s elapsed, ${remaining}s remaining), next check in ${delay / 1000}s`
    )
    await sleep(delay)
  }

  // Max wait time exceeded
  const elapsed = Math.round((Date.now() - startTime) / 1000)
  conn.status = "error"
  conn.errorMessage = `SDK did not become ready after ${elapsed} seconds (${attempt} attempts)`
  broadcastToClients(conn, {
    type: "status",
    status: "error",
    error: conn.errorMessage,
  })
  console.error(`[SDK-WS] ${conn.errorMessage} for ${conn.containerId}`)
  return false
}

// =============================================================================
// SDK Polling
// =============================================================================

async function fetchSDKData(
  sdkUrl: string,
  endpoint: string
): Promise<unknown | null> {
  try {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 5000)

    const response = await fetch(`${sdkUrl}${endpoint}`, {
      signal: controller.signal,
    })

    clearTimeout(timeoutId)

    if (!response.ok) {
      return null
    }

    return await response.json()
  } catch (error) {
    return null
  }
}

async function pollSDK(conn: SDKConnection): Promise<void> {
  if (!conn.sdkUrl || conn.clients.size === 0 || conn.isPolling) {
    return
  }

  conn.isPolling = true
  let hasChanges = false

  try {
    // 1. Fetch agent dialog (most frequent updates)
    const dialogData = (await fetchSDKData(
      conn.sdkUrl,
      `/agent/dialog${conn.dialogLastSeq >= 0 ? `?since=${conn.dialogLastSeq}` : ""}`
    )) as { entries?: DialogEntry[] } | null

    if (dialogData?.entries && dialogData.entries.length > 0) {
      hasChanges = true
      const newEntries = dialogData.entries
      conn.dialogEntries = [...conn.dialogEntries, ...newEntries]
      conn.dialogLastSeq = Math.max(...newEntries.map((e) => e.seq))
      broadcastToClients(conn, {
        type: "dialog",
        entries: newEntries,
        lastSeq: conn.dialogLastSeq,
      })
    }

    // 2. Fetch files and diff (check for changes)
    const [filesData, diffData] = await Promise.all([
      fetchSDKData(conn.sdkUrl, "/files") as Promise<{
        files?: ChangedFile[]
      } | null>,
      fetchSDKData(conn.sdkUrl, "/diff") as Promise<{ diff?: string } | null>,
    ])

    if (filesData?.files) {
      const filesJson = JSON.stringify(filesData.files)
      const cachedFilesJson = JSON.stringify(conn.files)
      if (filesJson !== cachedFilesJson) {
        hasChanges = true
        conn.files = filesData.files
        broadcastToClients(conn, { type: "files", files: filesData.files })
      }
    }

    if (diffData?.diff !== undefined) {
      if (diffData.diff !== conn.diff) {
        hasChanges = true
        conn.diff = diffData.diff
        broadcastToClients(conn, { type: "diff", diff: diffData.diff })
      }
    }

    // 3. Check evaluation result (only if not already available)
    if (!conn.result?.available) {
      const resultData = (await fetchSDKData(
        conn.sdkUrl,
        "/result"
      )) as EvaluationResultResponse | null

      if (resultData) {
        // Always update result data (might have partial info before available=true)
        const resultChanged =
          JSON.stringify(resultData) !== JSON.stringify(conn.result)
        if (resultChanged) {
          hasChanges = true
          conn.result = resultData
          broadcastToClients(conn, { type: "result", result: resultData })
        }
      }
    }

    // Update activity timestamp
    if (hasChanges) {
      conn.lastActivity = Date.now()
    }
  } catch (error) {
    console.error(`[SDK-WS] Poll error for ${conn.containerId}:`, error)
  } finally {
    conn.isPolling = false
  }

  // Schedule next poll with adaptive interval
  if (conn.clients.size > 0 && conn.status === "ready") {
    const interval = getAdaptivePollInterval(conn)
    conn.pollTimeout = setTimeout(() => pollSDK(conn), interval)
  }
}

// =============================================================================
// Initial Data Fetch
// =============================================================================

async function fetchInitialData(conn: SDKConnection): Promise<void> {
  if (!conn.sdkUrl) return

  try {
    // Fetch all initial data in parallel
    const [
      projectData,
      filesData,
      diffData,
      dialogData,
      resultData,
      versionData,
    ] = await Promise.all([
      fetchSDKData(conn.sdkUrl, "/project") as Promise<ProjectInfo | null>,
      fetchSDKData(conn.sdkUrl, "/files") as Promise<{
        files?: ChangedFile[]
      } | null>,
      fetchSDKData(conn.sdkUrl, "/diff") as Promise<{ diff?: string } | null>,
      fetchSDKData(conn.sdkUrl, "/agent/dialog") as Promise<{
        entries?: DialogEntry[]
      } | null>,
      fetchSDKData(
        conn.sdkUrl,
        "/result"
      ) as Promise<EvaluationResultResponse | null>,
      fetchSDKData(conn.sdkUrl, "/version") as Promise<{
        version?: string
      } | null>,
    ])

    // Broadcast SDK ready status with version
    broadcastToClients(conn, {
      type: "status",
      status: "ready",
      sdkVersion: versionData?.version,
    })

    // Broadcast project info
    if (projectData) {
      conn.project = projectData
      broadcastToClients(conn, { type: "project", data: projectData })
    }

    // Broadcast files
    if (filesData?.files) {
      conn.files = filesData.files
      broadcastToClients(conn, { type: "files", files: filesData.files })
    }

    // Broadcast diff
    if (diffData?.diff !== undefined) {
      conn.diff = diffData.diff
      broadcastToClients(conn, { type: "diff", diff: diffData.diff })
    }

    // Broadcast dialog entries
    if (dialogData?.entries && dialogData.entries.length > 0) {
      conn.dialogEntries = dialogData.entries
      conn.dialogLastSeq = Math.max(...dialogData.entries.map((e) => e.seq))
      broadcastToClients(conn, {
        type: "dialog",
        entries: dialogData.entries,
        lastSeq: conn.dialogLastSeq,
      })
    }

    // Broadcast result
    if (resultData) {
      conn.result = resultData
      broadcastToClients(conn, { type: "result", result: resultData })
    }

    conn.lastActivity = Date.now()
  } catch (error) {
    console.error(
      `[SDK-WS] Initial fetch error for ${conn.containerId}:`,
      error
    )
    broadcastToClients(conn, {
      type: "error",
      error: "Failed to fetch initial SDK data",
    })
  }
}

// =============================================================================
// Public API
// =============================================================================

/**
 * Start SDK WebSocket connection for a container
 */
export async function startSDKConnection(
  containerId: string,
  ws: ServerWebSocket<unknown>
): Promise<void> {
  console.log(`[SDK-WS] Client connecting for container: ${containerId}`)

  // Check if connection already exists for this container
  let conn = connections.get(containerId)

  if (conn) {
    // Add client to existing connection
    conn.clients.add(ws)
    console.log(
      `[SDK-WS] Added client to existing connection (${conn.clients.size} clients)`
    )

    // Send current state to new client
    if (conn.status === "ready") {
      ws.send(JSON.stringify({ type: "status", status: "ready" }))

      // Send cached data
      if (conn.project) {
        ws.send(JSON.stringify({ type: "project", data: conn.project }))
      }
      if (conn.files.length > 0) {
        ws.send(JSON.stringify({ type: "files", files: conn.files }))
      }
      if (conn.diff) {
        ws.send(JSON.stringify({ type: "diff", diff: conn.diff }))
      }
      if (conn.dialogEntries.length > 0) {
        ws.send(
          JSON.stringify({
            type: "dialog",
            entries: conn.dialogEntries,
            lastSeq: conn.dialogLastSeq,
          })
        )
      }
      if (conn.result) {
        ws.send(JSON.stringify({ type: "result", result: conn.result }))
      }
    } else if (conn.status === "connecting") {
      ws.send(JSON.stringify({ type: "status", status: "connecting" }))
    } else if (conn.status === "error") {
      ws.send(
        JSON.stringify({
          type: "status",
          status: "error",
          error: conn.errorMessage,
        })
      )
    }

    return
  }

  // Create new connection
  conn = {
    containerId,
    clients: new Set([ws]),
    status: "connecting",
    sdkUrl: null,
    errorMessage: null,
    project: null,
    files: [],
    diff: "",
    dialogLastSeq: -1,
    dialogEntries: [],
    result: null,
    pollTimeout: null,
    lastActivity: Date.now(),
    isPolling: false,
  }
  connections.set(containerId, conn)

  // Send initial connecting status
  broadcastToClients(conn, { type: "status", status: "connecting" })

  // Wait for SDK to be ready
  const ready = await waitForSDKReady(conn)
  if (!ready) {
    return
  }

  // Fetch initial data
  await fetchInitialData(conn)

  // Start polling
  const interval = getAdaptivePollInterval(conn)
  conn.pollTimeout = setTimeout(() => pollSDK(conn), interval)
}

/**
 * Stop SDK WebSocket connection for a client
 */
export function stopSDKConnection(
  containerId: string,
  ws: ServerWebSocket<unknown>
): void {
  const conn = connections.get(containerId)
  if (!conn) return

  conn.clients.delete(ws)
  console.log(
    `[SDK-WS] Client disconnected for ${containerId} (${conn.clients.size} remaining)`
  )

  // If no more clients, clean up
  if (conn.clients.size === 0) {
    console.log(
      `[SDK-WS] No clients remaining, cleaning up connection for ${containerId}`
    )

    if (conn.pollTimeout) {
      clearTimeout(conn.pollTimeout)
      conn.pollTimeout = null
    }

    connections.delete(containerId)
  }
}

/**
 * Shutdown all SDK connections (for graceful server shutdown)
 */
export function shutdownAllSDKConnections(): void {
  console.log(`[SDK-WS] Shutting down ${connections.size} connections`)

  for (const [_containerId, conn] of connections) {
    if (conn.pollTimeout) {
      clearTimeout(conn.pollTimeout)
    }

    for (const client of conn.clients) {
      try {
        client.close()
      } catch {
        // Ignore close errors
      }
    }
  }

  connections.clear()
}

/**
 * Get stats for debugging
 */
export function getSDKConnectionStats(): {
  totalConnections: number
  connections: Array<{
    containerId: string
    clientCount: number
    status: string
    lastActivity: number
  }>
} {
  return {
    totalConnections: connections.size,
    connections: Array.from(connections.entries()).map(([id, conn]) => ({
      containerId: id,
      clientCount: conn.clients.size,
      status: conn.status,
      lastActivity: conn.lastActivity,
    })),
  }
}
