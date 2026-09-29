/**
 * PTY Session Management for Docker Container Terminals
 *
 * Manages pseudo-terminal sessions that connect to Docker containers
 * via Go PTY proxy subprocess. The proxy provides true PTY support
 * using creack/pty library and communicates via stdin/stdout JSON.
 *
 * Architecture:
 * - Bun server handles WebSocket connections from frontend
 * - Spawns Go PTY proxy subprocess per container session
 * - Bridges WebSocket ↔ subprocess stdin/stdout (JSON messages)
 * - Go subprocess creates real PTY for `docker exec -it <container> bash`
 *
 * Features:
 * - True PTY support with proper resize handling
 * - Process tracking for all spawned PTY proxy processes
 * - Periodic orphan cleanup for leaked processes
 * - Graceful shutdown handling
 * - Activity tracking to detect idle sessions
 */

import type { ServerWebSocket } from "bun"
import { existsSync } from "fs"
import { join } from "path"
import { getContainer } from "./docker"

// =============================================================================
// Configuration
// =============================================================================

/** Built from source by `bun run build:pty`; not checked in */
const PTY_PROXY_BIN = join(import.meta.dir, "..", "pty-proxy", "pty-proxy")

const config = {
  /** Interval for orphan cleanup (ms) */
  CLEANUP_INTERVAL: parseInt(process.env.PTY_CLEANUP_INTERVAL || "30000"), // 30s
  /** Time without activity before a session is considered orphaned (ms) */
  ORPHAN_THRESHOLD: parseInt(process.env.PTY_ORPHAN_THRESHOLD || "300000"), // 5min
  /** Enable periodic orphan cleanup */
  ENABLE_CLEANUP: process.env.PTY_ENABLE_CLEANUP !== "false",
}

// =============================================================================
// Types
// =============================================================================

/**
 * Message types for WebSocket communication
 */
type ClientMessage =
  | { type: "input"; data: string }
  | { type: "resize"; cols: number; rows: number }

type ServerMessage =
  | { type: "output"; data: string }
  | { type: "error"; message: string }
  | { type: "exit"; code: number | null }

/**
 * PTY Session - represents a single terminal connection to a container
 */
interface PTYSession {
  id: string
  containerId: string
  process: ReturnType<typeof Bun.spawn>
  cols: number
  rows: number
  createdAt: Date
  lastActivity: Date
}

/**
 * Tracked process info for orphan detection
 */
interface TrackedProcess {
  pid: number
  containerId: string
  sessionId: string
  startedAt: Date
}

// =============================================================================
// State
// =============================================================================

/** Session storage - maps session ID to PTYSession */
const sessions = new Map<string, PTYSession>()

/** WebSocket to Session mapping - for cleanup on disconnect */
const wsToSession = new Map<ServerWebSocket<unknown>, string>()

/** Session to WebSocket mapping - for orphan detection */
const sessionToWs = new Map<string, ServerWebSocket<unknown>>()

/** Tracked processes - maps PID to tracking info */
const trackedProcesses = new Map<number, TrackedProcess>()

/** Cleanup interval handle */
let cleanupIntervalHandle: ReturnType<typeof setInterval> | null = null

// =============================================================================
// Helpers
// =============================================================================

/**
 * Generate a unique session ID
 */
function generateSessionId(): string {
  return `pty-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`
}

/**
 * Check if a process is still alive
 */
function isProcessAlive(pid: number): boolean {
  try {
    // Signal 0 doesn't kill, just checks if process exists
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

/**
 * Send a message to WebSocket
 */
function sendMessage(
  ws: ServerWebSocket<unknown>,
  message: ServerMessage
): void {
  try {
    ws.send(JSON.stringify(message))
  } catch (error) {
    console.error("[PTY] Failed to send message:", error)
  }
}

/**
 * Update session activity timestamp
 */
function updateActivity(session: PTYSession): void {
  session.lastActivity = new Date()
}

// =============================================================================
// Session Management
// =============================================================================

/**
 * Create a new PTY session for a container
 *
 * Spawns `docker exec -it <containerId> <command>` and sets up stream handling.
 */
export async function createPTYSession(
  containerId: string,
  ws: ServerWebSocket<unknown>,
  cols: number = 80,
  rows: number = 24,
  command: string = "bash",
  workDir?: string
): Promise<PTYSession | null> {
  // Validate container exists and is running
  const container = await getContainer(containerId)
  if (!container) {
    sendMessage(ws, {
      type: "error",
      message: `Container ${containerId} not found`,
    })
    return null
  }

  if (container.status !== "running") {
    sendMessage(ws, {
      type: "error",
      message: `Container is not running (status: ${container.status}). Start it with: docker start ${containerId}`,
    })
    return null
  }

  if (!existsSync(PTY_PROXY_BIN)) {
    sendMessage(ws, {
      type: "error",
      message:
        "Terminal unavailable: pty-proxy is not built. Run `bun run build:pty` in webui/.",
    })
    return null
  }

  const sessionId = generateSessionId()
  const now = new Date()

  try {
    // Spawn Go PTY proxy as subprocess
    // The Go binary creates a real PTY using creack/pty library
    // Communication is via stdin/stdout with JSON messages
    const args = [PTY_PROXY_BIN]

    // Add command flag if not bash
    if (command !== "bash") {
      args.push("--cmd", command)
    }

    // Add working directory flag if specified
    if (workDir) {
      args.push("--workdir", workDir)
    }

    // Add container ID (must be last)
    args.push(containerId)

    const proc = Bun.spawn({
      cmd: args,
      stdin: "pipe",
      stdout: "pipe",
      stderr: "pipe",
      env: {
        ...Bun.env,
      },
    })

    const session: PTYSession = {
      id: sessionId,
      containerId,
      process: proc,
      cols,
      rows,
      createdAt: now,
      lastActivity: now,
    }

    // Store session mappings
    sessions.set(sessionId, session)
    wsToSession.set(ws, sessionId)
    sessionToWs.set(sessionId, ws)

    // Track the process
    if (proc.pid) {
      trackedProcesses.set(proc.pid, {
        pid: proc.pid,
        containerId,
        sessionId,
        startedAt: now,
      })
      console.log(
        `[PTY] Tracking process PID ${proc.pid} for session ${sessionId}`
      )
    }

    // Stream stdout to WebSocket (JSON messages from Go PTY proxy)
    streamOutput(session, ws, proc.stdout)

    // Log stderr for debugging (Go proxy logs, not JSON)
    streamStderrToConsole(session, proc.stderr)

    // Handle process exit
    proc.exited.then((code) => {
      console.log(`[PTY] Session ${sessionId} exited with code ${code}`)
      sendMessage(ws, { type: "exit", code })
      cleanupSession(sessionId)
    })

    console.log(
      `[PTY] Created session ${sessionId} for container ${containerId} (PID: ${proc.pid})`
    )
    return session
  } catch (error) {
    console.error(`[PTY] Failed to create session:`, error)
    sendMessage(ws, {
      type: "error",
      message: `Failed to start terminal: ${error instanceof Error ? error.message : "Unknown error"}`,
    })
    return null
  }
}

/**
 * Stream output from Go PTY proxy subprocess (JSON lines) to WebSocket
 */
async function streamOutput(
  session: PTYSession,
  ws: ServerWebSocket<unknown>,
  stream: ReadableStream<Uint8Array>
): Promise<void> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const chunk = decoder.decode(value, { stream: true })
      buffer += chunk

      // Process complete JSON lines
      let newlineIndex: number
      while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
        const line = buffer.slice(0, newlineIndex).trim()
        buffer = buffer.slice(newlineIndex + 1)

        if (line) {
          try {
            // Parse JSON message from Go subprocess
            const message: ServerMessage = JSON.parse(line)
            // Update activity on output
            updateActivity(session)
            // Forward to WebSocket
            sendMessage(ws, message)
          } catch (error) {
            // This shouldn't happen if Go proxy is working correctly
            // Log but don't spam - this might be a malformed message
            console.warn(
              `[PTY] Failed to parse JSON from stdout (ignoring): ${line.slice(0, 100)}`
            )
          }
        }
      }
    }
  } catch (error) {
    // Stream closed, this is expected on session end
    if (sessions.has(session.id)) {
      console.error(`[PTY] Stream error for session ${session.id}:`, error)
    }
  }
}

/**
 * Stream stderr from Go PTY proxy to console (for debugging)
 *
 * The Go proxy outputs debug logs to stderr (with [PTY-PROXY] prefix).
 * These are not JSON and should not be parsed or sent to WebSocket.
 */
async function streamStderrToConsole(
  session: PTYSession,
  stream: ReadableStream<Uint8Array>
): Promise<void> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const chunk = decoder.decode(value, { stream: true })
      buffer += chunk

      // Process complete lines
      let newlineIndex: number
      while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
        const line = buffer.slice(0, newlineIndex).trim()
        buffer = buffer.slice(newlineIndex + 1)

        if (line) {
          // Log Go proxy debug output to console (not to WebSocket)
          console.log(`[PTY:${session.id.slice(-8)}] ${line}`)
        }
      }
    }
  } catch {
    // Stream closed, expected on session end
  }
}

/**
 * Handle incoming WebSocket message
 */
export function handleMessage(
  ws: ServerWebSocket<unknown>,
  rawData: string | Buffer
): void {
  const sessionId = wsToSession.get(ws)
  if (!sessionId) {
    console.warn("[PTY] Received message for unknown WebSocket")
    return
  }

  const session = sessions.get(sessionId)
  if (!session) {
    console.warn(`[PTY] Session ${sessionId} not found`)
    return
  }

  // Update activity on any message
  updateActivity(session)

  try {
    const data = typeof rawData === "string" ? rawData : rawData.toString()
    const message: ClientMessage = JSON.parse(data)

    switch (message.type) {
      case "input":
        handleInput(session, message.data)
        break
      case "resize":
        handleResize(session, message.cols, message.rows)
        break
      default:
        console.warn(`[PTY] Unknown message type:`, message)
    }
  } catch (error) {
    console.error("[PTY] Failed to parse message:", error)
  }
}

/**
 * Handle terminal input - send as JSON to Go subprocess stdin
 */
function handleInput(session: PTYSession, data: string): void {
  const stdin = session.process.stdin
  if (stdin && typeof stdin !== "number") {
    const message: ClientMessage = { type: "input", data }
    const json = JSON.stringify(message) + "\n"
    stdin.write(new TextEncoder().encode(json))
  }
}

/**
 * Handle terminal resize - send as JSON to Go subprocess stdin
 */
function handleResize(session: PTYSession, cols: number, rows: number): void {
  session.cols = cols
  session.rows = rows

  // Send resize command to Go subprocess
  const stdin = session.process.stdin
  if (stdin && typeof stdin !== "number") {
    const message: ClientMessage = { type: "resize", cols, rows }
    const json = JSON.stringify(message) + "\n"
    stdin.write(new TextEncoder().encode(json))

    console.log(`[PTY] Session ${session.id} resize: ${cols}x${rows}`)
  }
}

/**
 * Clean up a session and its associated process
 */
function cleanupSession(sessionId: string): void {
  const session = sessions.get(sessionId)
  if (!session) return

  const pid = session.process.pid

  // Kill the process if still running
  try {
    session.process.kill()
    console.log(`[PTY] Killed process PID ${pid} for session ${sessionId}`)
  } catch {
    // Process may already be dead
  }

  // Remove from tracking
  if (pid) {
    trackedProcesses.delete(pid)
  }

  // Clean up all mappings
  sessions.delete(sessionId)
  sessionToWs.delete(sessionId)

  console.log(`[PTY] Cleaned up session ${sessionId}`)
}

/**
 * Handle WebSocket close - clean up associated session
 */
export function handleClose(ws: ServerWebSocket<unknown>): void {
  const sessionId = wsToSession.get(ws)
  if (sessionId) {
    console.log(`[PTY] WebSocket closed for session ${sessionId}`)
    cleanupSession(sessionId)
    wsToSession.delete(ws)
  }
}

// =============================================================================
// Orphan Cleanup
// =============================================================================

/**
 * Clean up orphaned processes (no active WebSocket, idle too long)
 */
function cleanupOrphanedProcesses(): void {
  const now = Date.now()
  let orphansKilled = 0

  for (const [pid, tracked] of trackedProcesses.entries()) {
    const session = sessions.get(tracked.sessionId)
    const ws = sessionToWs.get(tracked.sessionId)

    // Check if process is actually alive
    if (!isProcessAlive(pid)) {
      // Process already dead, just remove from tracking
      trackedProcesses.delete(pid)
      console.log(`[PTY] Removed dead process PID ${pid} from tracking`)
      continue
    }

    // Check if WebSocket is still connected
    const hasActiveWebSocket = session && ws

    if (!hasActiveWebSocket) {
      // No WebSocket means orphaned - check idle time
      const idleTime = session
        ? now - session.lastActivity.getTime()
        : now - tracked.startedAt.getTime()

      if (idleTime > config.ORPHAN_THRESHOLD) {
        console.log(
          `[PTY] Killing orphaned process PID ${pid} (idle ${Math.round(idleTime / 1000)}s, container: ${tracked.containerId})`
        )
        try {
          process.kill(pid, "SIGKILL")
          orphansKilled++
        } catch (err) {
          console.error(`[PTY] Failed to kill process PID ${pid}:`, err)
        }
        trackedProcesses.delete(pid)

        // Also clean up session if it exists
        if (session) {
          sessions.delete(tracked.sessionId)
          sessionToWs.delete(tracked.sessionId)
        }
      }
    }
  }

  if (orphansKilled > 0) {
    console.log(`[PTY] Orphan cleanup: killed ${orphansKilled} processes`)
  }
}

/**
 * Start the periodic orphan cleanup
 */
function startCleanupInterval(): void {
  if (!config.ENABLE_CLEANUP) {
    console.log("[PTY] Orphan cleanup disabled via PTY_ENABLE_CLEANUP=false")
    return
  }

  if (cleanupIntervalHandle) {
    clearInterval(cleanupIntervalHandle)
  }

  cleanupIntervalHandle = setInterval(
    cleanupOrphanedProcesses,
    config.CLEANUP_INTERVAL
  )

  console.log(
    `[PTY] Started orphan cleanup (interval: ${config.CLEANUP_INTERVAL}ms, threshold: ${config.ORPHAN_THRESHOLD}ms)`
  )
}

/**
 * Stop the periodic orphan cleanup
 */
function stopCleanupInterval(): void {
  if (cleanupIntervalHandle) {
    clearInterval(cleanupIntervalHandle)
    cleanupIntervalHandle = null
  }
}

// Start cleanup on module load
startCleanupInterval()

// =============================================================================
// Graceful Shutdown
// =============================================================================

/**
 * Shutdown all PTY sessions gracefully
 *
 * Should be called on SIGINT/SIGTERM to prevent orphaned processes.
 */
export function shutdownAllSessions(): void {
  console.log(`[PTY] Shutting down ${sessions.size} active sessions...`)

  // Stop cleanup interval
  stopCleanupInterval()

  // Kill all tracked processes
  for (const [pid, tracked] of trackedProcesses.entries()) {
    try {
      console.log(
        `[PTY] Killing process PID ${pid} (container: ${tracked.containerId})`
      )
      process.kill(pid, "SIGKILL")
    } catch (err) {
      // Process may already be dead
      console.error(`[PTY] Failed to kill process PID ${pid}:`, err)
    }
  }

  // Close all WebSockets
  for (const [ws, sessionId] of wsToSession.entries()) {
    try {
      ws.close(1001, "Server shutting down")
    } catch (err) {
      console.error(
        `[PTY] Failed to close WebSocket for session ${sessionId}:`,
        err
      )
    }
  }

  // Clear all maps
  sessions.clear()
  wsToSession.clear()
  sessionToWs.clear()
  trackedProcesses.clear()

  console.log("[PTY] All sessions cleaned up")
}

// =============================================================================
// Monitoring / Debugging
// =============================================================================

/**
 * Get process tracking stats
 */
export function getProcessStats(): {
  activeSessions: number
  trackedProcesses: number
  processes: Array<{
    pid: number
    containerId: string
    sessionId: string
    uptimeMs: number
  }>
} {
  const now = Date.now()
  return {
    activeSessions: sessions.size,
    trackedProcesses: trackedProcesses.size,
    processes: Array.from(trackedProcesses.entries()).map(([pid, tracked]) => ({
      pid,
      containerId: tracked.containerId,
      sessionId: tracked.sessionId,
      uptimeMs: now - tracked.startedAt.getTime(),
    })),
  }
}
