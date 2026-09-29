/**
 * OpenCode SDK Integration - Manages OpenCode SDK clients for containers
 *
 * OpenCode server runs on port 4096 inside each container.
 * This module provides type-safe SDK access to containerized OpenCode servers.
 *
 * Features:
 * - SDK client management: Creates and caches SDK clients per container
 * - Auto-start: Automatically starts OpenCode server in containers if not running
 * - Process management: Tracks spawned OpenCode processes (not detached)
 * - Lifecycle management: Cleans up processes on shutdown
 */

import { getSDKUrl, resolveContainer } from "./docker"
import { spawn } from "bun"
import {
  createOpencodeClient,
  type Event,
  type OpencodeClient,
} from "@opencode-ai/sdk"

/**
 * OpenCode process info - tracks a spawned OpenCode server process
 */
interface OpenCodeProcess {
  containerId: string
  process: ReturnType<typeof spawn>
  startedAt: Date
  isStarting: boolean // prevent concurrent start attempts
}

/**
 * In-memory map to track OpenCode processes per container
 */
const openCodeProcesses = new Map<string, OpenCodeProcess>()

/**
 * In-memory map to cache SDK clients per container
 */
const sdkClients = new Map<string, OpencodeClient>()

/**
 * In-memory map to track which directory each session was created in
 * This is needed because OpenCode requires the x-opencode-directory header
 * on all operations, not just session creation
 */
const sessionDirectories = new Map<string, string | undefined>()

/**
 * Check if OpenCode server is running for a container
 *
 * Checks network connectivity first (works for both tracked and orphaned processes).
 * Falls back to process state check for tracked processes.
 *
 * @param containerId Container ID
 * @returns true if OpenCode is responding to requests
 */
async function isOpenCodeRunning(containerId: string): Promise<boolean> {
  // First, try network check - this works for both tracked and orphaned processes
  try {
    const openCodeUrl = await getOpenCodeUrl(containerId)
    if (!openCodeUrl) return false

    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 2000) // 2s timeout

    const response = await fetch(`${openCodeUrl}/session`, {
      method: "GET",
      signal: controller.signal,
    })

    clearTimeout(timeoutId)

    // Must be 200 OK
    if (!response.ok) return false

    // Must return valid JSON (array of sessions)
    try {
      const data = await response.json()
      if (Array.isArray(data)) {
        // OpenCode is running! If we don't have it tracked, it's orphaned
        const processInfo = openCodeProcesses.get(containerId)
        if (!processInfo) {
          const logPrefix = `[OpenCode:${containerId.substring(0, 12)}]`
          console.log(
            `${logPrefix} Detected orphaned OpenCode process, will reuse it`
          )
        }
        return true
      }
    } catch {
      // Not valid JSON - OpenCode might still be initializing
      return false
    }
  } catch {
    // Network check failed - OpenCode not responding
  }

  // Network check failed, check if we have a tracked process that's starting up
  const processInfo = openCodeProcesses.get(containerId)
  if (!processInfo) return false

  // Check if tracked process is still alive
  if (processInfo.process.killed || processInfo.process.exitCode !== null) {
    // Process died, clean up
    openCodeProcesses.delete(containerId)
    return false
  }

  // Process exists and is still alive, might be starting up
  return processInfo.isStarting
}

/**
 * Stream output from subprocess to console
 */
async function streamOutput(
  stream: ReadableStream | null,
  containerId: string,
  type: "stdout" | "stderr"
) {
  if (!stream || typeof stream === "number") return

  const logPrefix = `[OpenCode:${containerId.substring(0, 12)}]`
  const reader = stream.getReader()

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const text = new TextDecoder().decode(value)
      const lines = text.split("\n").filter((l) => l.trim())

      for (const line of lines) {
        console.log(`${logPrefix}[${type}] ${line}`)
      }
    }
  } catch (error) {
    // Stream closed or error
    console.error(`${logPrefix} Stream error:`, error)
  }
}

/**
 * Start OpenCode server in a container using Bun.spawn
 *
 * Spawns docker exec without -d flag so we can manage the process.
 * If OpenCode is already running in the container (orphaned), connects to it.
 *
 * @param containerId Container ID
 * @returns true if started successfully
 */
async function startOpenCode(containerId: string): Promise<boolean> {
  const logPrefix = `[OpenCode:${containerId.substring(0, 12)}]`

  // Check if already starting
  const existing = openCodeProcesses.get(containerId)
  if (existing?.isStarting) {
    console.log(`${logPrefix} Already starting, waiting...`)
    return false
  }

  // Check if OpenCode is already running in container (orphaned process)
  try {
    const openCodeUrl = await getOpenCodeUrl(containerId)
    if (openCodeUrl) {
      const response = await fetch(`${openCodeUrl}/session`, {
        signal: AbortSignal.timeout(2000),
      })
      if (response.ok) {
        const data = await response.json()
        if (Array.isArray(data)) {
          console.log(
            `${logPrefix} Detected existing OpenCode server, connecting...`
          )
          // Don't track this process since we didn't spawn it
          // The next health check will detect it's running
          return true
        }
      }
    }
  } catch {
    // No existing server, proceed with spawn
  }

  const container = await resolveContainer(containerId)
  if (!container) {
    console.error(`${logPrefix} Not an SSEBench container`)
    return false
  }

  try {
    console.log(`${logPrefix} Starting OpenCode server...`)

    // Spawn docker exec (without -d flag)
    const proc = spawn({
      cmd: [
        "docker",
        "exec",
        "-i", // Keep stdin open (even though we don't use it)
        // It listens on the run network, which other containers share, so
        // it gets the agent's privileges, not root's.
        "--user",
        "model",
        container.id,
        "opencode",
        "serve",
        "--port",
        "4096",
        "--hostname",
        "0.0.0.0",
        "--print-logs",
      ],
      stdin: "ignore",
      stdout: "pipe",
      stderr: "pipe",
      env: Bun.env,
    })

    // Store process info
    const processInfo: OpenCodeProcess = {
      containerId,
      process: proc,
      startedAt: new Date(),
      isStarting: true,
    }
    openCodeProcesses.set(containerId, processInfo)

    // Stream stdout to console
    streamOutput(proc.stdout, containerId, "stdout")

    // Stream stderr to console
    streamOutput(proc.stderr, containerId, "stderr")

    // Handle process exit
    proc.exited.then((code) => {
      console.log(`${logPrefix} Process exited with code ${code}`)
      openCodeProcesses.delete(containerId)
    })

    console.log(`${logPrefix} Process spawned (PID: ${proc.pid})`)

    // Poll for readiness - OpenCode needs time to initialize
    const maxWait = 10000 // 10 seconds max
    const pollInterval = 1000 // Check every 1 second
    const startTime = Date.now()

    while (Date.now() - startTime < maxWait) {
      await new Promise((resolve) => setTimeout(resolve, pollInterval))

      const isResponding = await isOpenCodeRunning(containerId)

      if (isResponding) {
        const elapsed = Math.floor((Date.now() - startTime) / 1000)
        console.log(
          `${logPrefix} OpenCode server started successfully (ready after ${elapsed}s)`
        )
        processInfo.isStarting = false
        return true
      }

      // Check if process died during startup
      if (proc.killed || proc.exitCode !== null) {
        console.error(`${logPrefix} Process died during startup`)
        processInfo.isStarting = false
        openCodeProcesses.delete(containerId)
        return false
      }
    }

    // Timeout - process is running but not responding
    console.warn(
      `${logPrefix} Process started but not responding after ${maxWait / 1000}s`
    )
    processInfo.isStarting = false
    openCodeProcesses.delete(containerId) // Clean up non-responsive process
    proc.kill() // Kill the unresponsive process
    return false
  } catch (error) {
    console.error(`${logPrefix} Failed to start OpenCode:`, error)
    openCodeProcesses.delete(containerId)
    return false
  }
}

/**
 * Ensure OpenCode server is running in container, starting it if necessary
 *
 * Checks if process exists and is alive. Starts if not running.
 *
 * @param containerId Container ID
 * @returns true if OpenCode is running, false if failed to start
 */
async function ensureOpenCodeRunning(containerId: string): Promise<boolean> {
  const logPrefix = `[OpenCode:${containerId.substring(0, 12)}]`

  // Check if already running
  const isRunning = await isOpenCodeRunning(containerId)

  if (isRunning) {
    return true
  }

  // Check if currently starting (prevent duplicate starts)
  const processInfo = openCodeProcesses.get(containerId)
  if (processInfo?.isStarting) {
    console.log(`${logPrefix} Already starting, waiting...`)
    // Wait a bit and return current state
    await new Promise((resolve) => setTimeout(resolve, 1000))
    return isOpenCodeRunning(containerId)
  }

  // Not running - attempt to start
  console.log(`${logPrefix} Starting OpenCode server...`)
  return startOpenCode(containerId)
}

/**
 * Get OpenCode server URL for a container
 *
 * OpenCode server runs on port 4096, similar to SDK on port 4263
 */
async function getOpenCodeUrl(containerId: string): Promise<string | null> {
  // Reuse SDK URL discovery logic, but change the port
  const sdkUrl = await getSDKUrl(containerId)
  if (!sdkUrl) return null

  // Replace SDK port (4263) with OpenCode port (4096)
  // Example: http://172.17.0.2:4263 -> http://172.17.0.2:4096
  return sdkUrl.replace(":4263", ":4096")
}

/**
 * Get or create SDK client for a container with optional working directory
 *
 * Auto-starts OpenCode server if not already running.
 * Caches SDK clients per (container + directory) for reuse.
 *
 * @param containerId Container ID
 * @param directory Optional working directory for OpenCode operations
 * @returns Configured OpenCode SDK client, or null if unavailable
 */
async function getSDKClient(
  containerId: string,
  directory?: string
): Promise<OpencodeClient | null> {
  const logPrefix = `[OpenCode:${containerId.substring(0, 12)}]`
  const cacheKey = directory ? `${containerId}:${directory}` : containerId

  // Always ensure OpenCode is running before returning client (even if cached)
  // This handles the case where OpenCode was stopped after the client was created
  const isRunning = await ensureOpenCodeRunning(containerId)
  if (!isRunning) {
    console.error(`${logPrefix} Failed to start OpenCode server`)
    // Clear cached client if OpenCode isn't running
    sdkClients.delete(cacheKey)
    return null
  }

  // Return cached client if exists
  if (sdkClients.has(cacheKey)) {
    return sdkClients.get(cacheKey)!
  }

  // Get OpenCode URL (reuses existing getOpenCodeUrl)
  const openCodeUrl = await getOpenCodeUrl(containerId)
  if (!openCodeUrl) {
    console.error(`${logPrefix} URL not accessible`)
    return null
  }

  // Create SDK client with optional directory
  // The directory is sent as x-opencode-directory header on all requests
  const client = createOpencodeClient({
    baseUrl: openCodeUrl,
    directory: directory,
    throwOnError: false, // Handle errors ourselves for consistency
  })

  // Cache it
  sdkClients.set(cacheKey, client)
  return client
}

/**
 * Create a new OpenCode session
 *
 * @param containerId Container ID
 * @param title Optional session title
 * @param workingDir Working directory for the session
 * @param apiKey Anthropic API key
 * @returns Session object
 */
export async function createSession(
  containerId: string,
  title?: string,
  workingDir?: string,
  apiKey?: string
): Promise<{ data: unknown; status: number }> {
  // Get SDK client with working directory
  // The directory is sent as x-opencode-directory header to tell OpenCode where to work
  const client = await getSDKClient(containerId, workingDir)
  if (!client) {
    return {
      data: { error: "OpenCode SDK client unavailable" },
      status: 503,
    }
  }

  try {
    // First, set the API key if provided
    if (apiKey) {
      const authResult = await client.auth.set({
        path: { id: "anthropic" },
        body: { type: "api", key: apiKey },
      })

      if (authResult.error) {
        console.error("[OpenCode] Failed to set API key:", authResult.error)
        // Continue anyway - session creation might still work if key was set before
      }
    }

    // Create session
    // Note: We pass directory via SDK client config (as header), not in query parameter
    // This tells OpenCode where to work without changing the project context
    const result = await client.session.create({
      body: {
        title: title || "Debug Session",
      },
    })

    if (result.error) {
      console.error("[OpenCode] Session creation error:", result.error)
      return { data: result.error, status: 400 }
    }

    // Validate that we actually got session data
    if (!result.data || typeof result.data !== "object" || !result.data.id) {
      console.error("[OpenCode] Invalid session data:", result.data)
      return {
        data: {
          error: "Failed to create session - invalid response from OpenCode",
        },
        status: 500,
      }
    }

    // Track which directory this session belongs to
    // This is needed for all future operations on this session
    sessionDirectories.set(result.data.id, workingDir)

    console.log(
      `[OpenCode] Session created: ${result.data.id}${workingDir ? ` in ${workingDir}` : ""}`
    )
    return { data: result.data, status: 200 }
  } catch (error) {
    console.error("SDK error in createSession:", error)
    return {
      data: { error: "Failed to create session: " + String(error) },
      status: 500,
    }
  }
}

/**
 * Send a message to a session
 *
 * @param containerId Container ID
 * @param sessionId Session ID
 * @param message Message text to send
 * @returns Assistant response
 */
export async function sendMessage(
  containerId: string,
  sessionId: string,
  message: string,
  directory?: string
): Promise<{ data: unknown; status: number }> {
  // Use provided directory, or look up from cache, or undefined
  const sessionDir = directory || sessionDirectories.get(sessionId)

  console.log(
    `[OpenCode] sendMessage - sessionId: ${sessionId}, directory: ${sessionDir || "none"}, message length: ${message.length}`
  )

  // Get SDK client with the directory
  const client = await getSDKClient(containerId, sessionDir)
  if (!client) {
    return {
      data: { error: "OpenCode SDK client unavailable" },
      status: 503,
    }
  }

  try {
    console.log(`[OpenCode] Calling session.prompt for session: ${sessionId}`)

    const result = await client.session.prompt({
      path: { id: sessionId },
      body: {
        parts: [{ type: "text", text: message }],
      },
    })

    console.log(
      `[OpenCode] session.prompt result:`,
      JSON.stringify(result, null, 2)
    )

    if (result.error) {
      console.error("[OpenCode] Message send error:", result.error)
      return { data: result.error, status: 400 }
    }

    // Return whatever we got - even if empty, the message might still be processing
    return { data: result.data || { status: "sent" }, status: 200 }
  } catch (error) {
    console.error("[OpenCode] SDK error in sendMessage:", error)
    return {
      data: { error: "Failed to send message: " + String(error) },
      status: 500,
    }
  }
}

/**
 * Get all messages in a session
 *
 * @param containerId Container ID
 * @param sessionId Session ID
 * @returns Array of messages
 */
export async function getMessages(
  containerId: string,
  sessionId: string
): Promise<{ data: unknown; status: number }> {
  // Look up the directory this session was created in
  const directory = sessionDirectories.get(sessionId)

  const client = await getSDKClient(containerId, directory)
  if (!client) {
    return {
      data: { error: "OpenCode SDK client unavailable" },
      status: 503,
    }
  }

  try {
    const result = await client.session.messages({
      path: { id: sessionId },
    })

    if (result.error) {
      return { data: result.error, status: 400 }
    }

    // Debug: Log raw SDK response to inspect date format
    console.log(
      "[OpenCode] Raw SDK messages response:",
      JSON.stringify(result.data, null, 2)
    )

    return { data: result.data, status: 200 }
  } catch (error) {
    console.error("SDK error in getMessages:", error)
    return {
      data: { error: "Failed to get messages: " + String(error) },
      status: 500,
    }
  }
}

/**
 * Get session details
 *
 * @param containerId Container ID
 * @param sessionId Session ID
 * @returns Session object
 */
export async function getSession(
  containerId: string,
  sessionId: string
): Promise<{ data: unknown; status: number }> {
  // Look up the directory this session was created in
  const directory = sessionDirectories.get(sessionId)

  const client = await getSDKClient(containerId, directory)
  if (!client) {
    return {
      data: { error: "OpenCode SDK client unavailable" },
      status: 503,
    }
  }

  try {
    const result = await client.session.messages({
      path: { id: sessionId },
    })

    if (result.error) {
      return { data: result.error, status: 400 }
    }

    return { data: result.data, status: 200 }
  } catch (error) {
    console.error("SDK error in getSession:", error)
    return {
      data: { error: "Failed to get session: " + String(error) },
      status: 500,
    }
  }
}

/**
 * Delete a session
 *
 * @param containerId Container ID
 * @param sessionId Session ID
 * @returns Success boolean
 */
export async function deleteSession(
  containerId: string,
  sessionId: string
): Promise<{ data: unknown; status: number }> {
  // Look up the directory this session was created in
  const directory = sessionDirectories.get(sessionId)

  const client = await getSDKClient(containerId, directory)
  if (!client) {
    return {
      data: { error: "OpenCode SDK client unavailable" },
      status: 503,
    }
  }

  try {
    const result = await client.session.delete({
      path: { id: sessionId },
    })

    if (result.error) {
      return { data: result.error, status: 404 }
    }

    // Clean up the directory mapping when session is deleted
    sessionDirectories.delete(sessionId)

    return { data: result.data, status: 200 }
  } catch (error) {
    console.error("SDK error in deleteSession:", error)
    return {
      data: { error: "Failed to delete session: " + String(error) },
      status: 500,
    }
  }
}

/**
 * List all sessions for a container
 *
 * @param containerId Container ID
 * @param directory Optional working directory to filter sessions
 * @returns List of sessions
 */
export async function listSessions(
  containerId: string,
  directory?: string
): Promise<{ data: unknown; status: number }> {
  // IMPORTANT: Use same directory as session creation
  // If directory is provided, get SDK client with that directory
  const client = await getSDKClient(containerId, directory)
  if (!client) {
    return {
      data: { error: "OpenCode SDK client unavailable" },
      status: 503,
    }
  }

  try {
    const result = await client.session.list()

    if (result.error) {
      return { data: result.error, status: 400 }
    }

    // Debug: Log what the SDK actually returns
    console.log(
      `[OpenCode] listSessions (directory: ${directory || "none"}):`,
      JSON.stringify(result.data, null, 2)
    )

    return { data: result.data, status: 200 }
  } catch (error) {
    console.error("SDK error in listSessions:", error)
    return {
      data: { error: "Failed to list sessions: " + String(error) },
      status: 500,
    }
  }
}

/**
 * Health check for OpenCode server
 *
 * Returns detailed status including process information.
 * Uses session.list() as health check since SDK has no dedicated health endpoint.
 *
 * @param containerId Container ID
 * @returns Health status with process details
 */
export async function checkHealth(containerId: string): Promise<{
  healthy: boolean
  version?: string
  processRunning?: boolean
  pid?: number
  uptime?: number
}> {
  const processInfo = openCodeProcesses.get(containerId)

  // Calculate uptime if process exists
  const uptime = processInfo
    ? Math.floor((Date.now() - processInfo.startedAt.getTime()) / 1000)
    : undefined

  // Try to get SDK client (will auto-start if needed)
  const client = await getSDKClient(containerId)
  if (!client) {
    return {
      healthy: false,
      processRunning: !!processInfo && !processInfo.process.killed,
      pid: processInfo?.process.pid,
      uptime,
    }
  }

  // Use session.list() as health check (SDK has no global.health())
  try {
    const result = await client.session.list()

    // If we get data without error, OpenCode is healthy
    const isHealthy = !result.error && result.data !== undefined

    // Extract version if available from first session
    const version =
      Array.isArray(result.data) && result.data.length > 0
        ? result.data[0].version
        : undefined

    // If OpenCode is healthy, it means a process is running (tracked or orphaned)
    const isProcessRunning =
      isHealthy || (!!processInfo && !processInfo.process.killed)

    return {
      healthy: isHealthy,
      version,
      processRunning: isProcessRunning,
      pid: processInfo?.process.pid,
      uptime,
    }
  } catch (error) {
    console.error("Health check error:", error)
    return {
      healthy: false,
      processRunning: !!processInfo && !processInfo.process.killed,
      pid: processInfo?.process.pid,
      uptime,
    }
  }
}

/**
 * Reply to a permission request
 *
 * Uses SDK method: session.postSessionIdPermissionsPermissionId
 *
 * @param containerId Container ID
 * @param sessionId Session ID
 * @param permissionId Permission request ID
 * @param allow Whether to allow the permission
 * @returns Success or error
 */
export async function replyToPermission(
  containerId: string,
  sessionId: string,
  permissionId: string,
  allow: boolean
): Promise<{ data: unknown; status: number }> {
  const logPrefix = `[OpenCode:${containerId.substring(0, 12)}]`

  // Look up the directory this session was created in
  const directory = sessionDirectories.get(sessionId)

  const client = await getSDKClient(containerId, directory)
  if (!client) {
    return {
      data: { error: "OpenCode SDK client unavailable" },
      status: 503,
    }
  }

  try {
    console.log(
      `${logPrefix} Replying to permission ${permissionId}: allow=${allow}`
    )

    // Use SDK method to reply to permission
    // response: "once" = allow this once, "always" = always allow, "reject" = deny
    const result = await client.postSessionIdPermissionsPermissionId({
      path: { id: sessionId, permissionID: permissionId },
      body: { response: allow ? "once" : "reject" },
      query: { directory },
    })

    if (result.error) {
      console.error(`${logPrefix} Permission reply error:`, result.error)
      return { data: result.error, status: 400 }
    }

    return { data: result.data ?? { success: true }, status: 200 }
  } catch (error) {
    console.error(`${logPrefix} Error in replyToPermission:`, error)
    return {
      data: { error: "Failed to reply to permission: " + String(error) },
      status: 500,
    }
  }
}

/**
 * Stream OpenCode session events via SSE
 *
 * Subscribes to OpenCode event stream and yields events.
 * Filters events by sessionId if provided.
 *
 * @param containerId Container ID
 * @param directory Working directory
 * @param sessionId Optional session ID to filter events
 * @returns AsyncGenerator of events, or null if unavailable
 */
export async function streamSessionEvents(
  containerId: string,
  directory?: string,
  sessionId?: string
): Promise<AsyncGenerator<Event> | null> {
  const logPrefix = `[OpenCode:${containerId.substring(0, 12)}]`

  // Get SDK client with working directory
  const client = await getSDKClient(containerId, directory)
  if (!client) {
    console.error(`${logPrefix} Cannot stream events - SDK client unavailable`)
    return null
  }

  try {
    console.log(
      `${logPrefix} Subscribing to event stream${sessionId ? ` (session: ${sessionId})` : ""}${directory ? ` (directory: ${directory})` : ""}`
    )

    // Subscribe to event stream from OpenCode SDK
    // The SDK returns ServerSentEventsResult which has a 'stream' property
    // Note: Directory is already configured in the SDK client, no need to pass it again
    const result = await client.event.subscribe()

    console.log(`${logPrefix} Event subscription result:`, {
      hasResult: !!result,
      hasStream: !!(result && result.stream),
    })

    if (!result || !result.stream) {
      console.error(`${logPrefix} No stream in event subscription response`)
      return null
    }

    console.log(`${logPrefix} Event stream created successfully`)

    // Create a filtered async generator if sessionId is provided
    async function* filteredStream() {
      try {
        for await (const event of result.stream) {
          // Filter by sessionId if provided
          if (sessionId) {
            // Not every event type carries a session
            const props = event?.properties as
              | {
                  sessionID?: string
                  part?: { sessionID?: string }
                  message?: { sessionID?: string }
                }
              | undefined
            const eventSessionId =
              props?.sessionID ||
              props?.part?.sessionID ||
              props?.message?.sessionID

            // Only yield events for this session
            if (eventSessionId && eventSessionId !== sessionId) {
              continue
            }
          }

          // Yield the event
          yield event
        }
      } catch (error) {
        console.error(`${logPrefix} Stream error:`, error)
        throw error
      }
    }

    return filteredStream()
  } catch (error) {
    console.error(`${logPrefix} Failed to subscribe to events:`, error)
    return null
  }
}

/**
 * Cleanup OpenCode processes on shutdown
 *
 * Kills all tracked OpenCode processes gracefully.
 */
export async function shutdownOpenCode(): Promise<void> {
  console.log(`[OpenCode] Shutting down ${openCodeProcesses.size} processes...`)

  const killPromises: Promise<void>[] = []

  for (const [containerId, processInfo] of openCodeProcesses.entries()) {
    const logPrefix = `[OpenCode:${containerId.substring(0, 12)}]`

    try {
      console.log(
        `${logPrefix} Terminating process (PID: ${processInfo.process.pid})`
      )
      processInfo.process.kill()

      // Wait for process to exit (with timeout)
      const exitPromise = Promise.race([
        processInfo.process.exited,
        new Promise((resolve) => setTimeout(resolve, 5000)), // 5s timeout
      ]).then(() => {
        console.log(`${logPrefix} Process terminated`)
      })

      killPromises.push(exitPromise as Promise<void>)
    } catch (error) {
      console.error(`${logPrefix} Failed to kill process:`, error)
    }
  }

  await Promise.all(killPromises)
  openCodeProcesses.clear()

  // Clear SDK client cache
  sdkClients.clear()

  console.log("[OpenCode] Shutdown complete")
}
