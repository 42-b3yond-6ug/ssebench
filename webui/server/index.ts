/**
 * SSEBench WebUI Backend Server
 *
 * A Bun server that:
 * - Uses Hono for REST API routes
 * - Uses Bun's native WebSocket for PTY connections
 */

import type { Server, ServerWebSocket } from "bun"
import { existsSync } from "fs"
import { Hono } from "hono"
import { cors } from "hono/cors"
import { logger } from "hono/logger"
import { serveStatic } from "hono/bun"
import { version } from "../package.json"
import {
  listContainers,
  getContainer,
  checkDockerAccess,
  getSDKUrl,
  checkSDKHealth,
  stopContainer,
  removeContainer,
  isContainerId,
  resolveContainer,
} from "./docker"
import { readReferencePatch } from "./reference"
import {
  createSession as createOpenCodeSession,
  sendMessage as sendOpenCodeMessage,
  getMessages as getOpenCodeMessages,
  getSession as getOpenCodeSession,
  listSessions as listOpenCodeSessions,
  deleteSession as deleteOpenCodeSession,
  checkHealth as checkOpenCodeHealth,
  replyToPermission as replyOpenCodePermission,
  streamSessionEvents,
  shutdownOpenCode,
} from "./opencode"
import {
  createPTYSession,
  handleMessage,
  handleClose,
  shutdownAllSessions,
  getProcessStats,
} from "./pty"
import {
  startContainerLogStream,
  stopContainerLogStream,
  shutdownAllLogStreams,
} from "./containerLogs"
import {
  startSDKConnection,
  stopSDKConnection,
  shutdownAllSDKConnections,
  getSDKConnectionStats,
} from "./sdkWebSocket"
import {
  getLocalTasks,
  getRemoteTasks,
  getModels,
  getAgents,
  hasLocalBenchmarks,
  isCatalogConfigured,
  CATALOG,
  CATALOG_NOT_CONFIGURED,
  launchTask,
  getLaunchStatus,
  getAllLaunchStatuses,
  getLaunchOutput,
  cancelLaunch,
  clearLaunchEntry,
  clearAllLaunches,
  subscribeToLaunch,
  unsubscribeFromLaunch,
  validateLaunchConfig,
  LOCAL_TASKS_PATH,
} from "./launch"
import {
  checkApiRequest,
  loadSecurityConfig,
  SecurityConfigError,
  webSocketResponseHeaders,
  type SecurityConfig,
} from "./security"

function loadSecurityOrExit(): SecurityConfig {
  try {
    return loadSecurityConfig()
  } catch (error) {
    if (error instanceof SecurityConfigError) {
      console.error(`[Server] ${error.message}`)
      process.exit(1)
    }
    throw error
  }
}

const security = loadSecurityOrExit()

// WebSocket data attached to each connection
interface WSData {
  containerId?: string
  type?:
    | "bash"
    | "debug"
    | "launch"
    | "container-logs"
    | "opencode-events"
    | "sdk" // Type of connection
  initialMessage?: string // Initial message to send to opencode (for debug type)
  sessionId?: string // Session ID for opencode-events
  directory?: string // Working directory for opencode-events
}

const app = new Hono()

// Middleware
app.use("*", logger())
app.use(
  "*",
  cors({
    // Same-origin requests need no CORS headers; other origins must be listed
    origin: (origin) => (security.corsOrigins.has(origin) ? origin : null),
    allowMethods: ["GET", "POST", "DELETE", "OPTIONS"],
    allowHeaders: ["Content-Type", "Cache-Control", "Authorization"],
    exposeHeaders: ["Content-Type", "Cache-Control"],
    credentials: false,
  })
)

// Registered here rather than in fetch() so the check sees the same
// (percent-decoded) path that the router uses.
app.use("/api/*", async (c, next) => {
  const rejection = checkApiRequest(c.req.raw, security)
  if (rejection) {
    console.warn(`[Auth] ${rejection.status} ${c.req.method} ${c.req.path}`)
    return rejection
  }
  await next()
})

// Container IDs reach the docker CLI; reject anything that is not one
app.use("/api/containers/:id/*", async (c, next) => {
  if (!isContainerId(c.req.param("id"))) {
    return c.json({ error: "Invalid container ID" }, 400)
  }
  await next()
})

// Health check
app.get("/api/health", async (c) => {
  const dockerOk = await checkDockerAccess()
  return c.json({
    status: "ok",
    version,
    docker: dockerOk,
    terminal: security.terminalEnabled,
    timestamp: new Date().toISOString(),
  })
})

// List all SSEBench containers
app.get("/api/containers", async (c) => {
  try {
    const containers = await listContainers()
    return c.json({ containers })
  } catch (error) {
    console.error("Error listing containers:", error)
    return c.json({ error: "Failed to list containers" }, 500)
  }
})

// Get single container by ID
app.get("/api/containers/:id", async (c) => {
  const id = c.req.param("id")
  try {
    const container = await getContainer(id)
    if (!container) {
      return c.json({ error: "Container not found" }, 404)
    }
    return c.json({ container })
  } catch (error) {
    console.error("Error getting container:", error)
    return c.json({ error: "Failed to get container" }, 500)
  }
})

// Stop a container
app.post("/api/containers/:id/stop", async (c) => {
  const id = c.req.param("id")
  try {
    const stopped = await stopContainer(id)
    if (!stopped) {
      return c.json({ error: "Failed to stop container" }, 500)
    }
    return c.json({ stopped: true })
  } catch (error) {
    console.error("Error stopping container:", error)
    return c.json({ error: "Failed to stop container" }, 500)
  }
})

// Remove a stopped container
app.post("/api/containers/:id/remove", async (c) => {
  const id = c.req.param("id")
  try {
    const removed = await removeContainer(id)
    if (!removed) {
      return c.json({ error: "Failed to remove container" }, 500)
    }
    return c.json({ removed: true })
  } catch (error) {
    console.error("Error removing container:", error)
    return c.json({ error: "Failed to remove container" }, 500)
  }
})

// PTY session monitoring endpoint (for debugging)
app.get("/api/pty/sessions", (c) => {
  const stats = getProcessStats()
  return c.json(stats)
})

// SDK WebSocket connection stats (for debugging)
app.get("/api/sdk/connections", (c) => {
  const stats = getSDKConnectionStats()
  return c.json(stats)
})

// =============================================================================
// SDK Proxy Routes - Forward requests to SDK daemon inside containers
// =============================================================================

/**
 * Helper: Proxy a request to SDK daemon in container
 *
 * Discovers the container's IP address and forwards the request to the SDK.
 * Returns both the response data and HTTP status code.
 */
async function proxyToSDK(
  containerId: string,
  endpoint: string
): Promise<{ data: unknown; status: number }> {
  const sdkUrl = await getSDKUrl(containerId)

  if (!sdkUrl) {
    return {
      data: { error: "SDK not accessible - container may not be running" },
      status: 503,
    }
  }

  try {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 5000) // 5s timeout

    const response = await fetch(`${sdkUrl}${endpoint}`, {
      signal: controller.signal,
    })

    clearTimeout(timeoutId)

    const data = await response.json()
    return { data, status: response.status }
  } catch (error) {
    console.error(`SDK proxy failed for ${sdkUrl}${endpoint}:`, error)

    if (error instanceof Error && error.name === "AbortError") {
      return {
        data: { error: "SDK request timeout" },
        status: 504,
      }
    }

    return {
      data: { error: "Failed to communicate with SDK daemon" },
      status: 500,
    }
  }
}

// Get project metadata (bug info, task description, etc.)
app.get("/api/containers/:id/project", async (c) => {
  const id = c.req.param("id")
  const { data, status } = await proxyToSDK(id, "/project")
  return c.json(data, status as 200 | 500 | 503 | 504)
})

// Get unified diff of all changes vs buggy commit
app.get("/api/containers/:id/diff", async (c) => {
  const id = c.req.param("id")
  const { data, status } = await proxyToSDK(id, "/diff")
  return c.json(data, status as 200 | 500 | 503 | 504)
})

// Get list of modified files with stats
app.get("/api/containers/:id/files", async (c) => {
  const id = c.req.param("id")
  const { data, status } = await proxyToSDK(id, "/files")
  return c.json(data, status as 200 | 500 | 503 | 504)
})

// SDK health check for a specific container
app.get("/api/containers/:id/sdk/health", async (c) => {
  const id = c.req.param("id")
  const sdkUrl = await getSDKUrl(id)

  if (!sdkUrl) {
    return c.json({ healthy: false, reason: "SDK URL not found" })
  }

  const healthy = await checkSDKHealth(sdkUrl)
  return c.json({ healthy, sdkUrl })
})

// Get SDK version for a specific container
app.get("/api/containers/:id/sdk/version", async (c) => {
  const id = c.req.param("id")
  const { data, status } = await proxyToSDK(id, "/version")
  return c.json(data, status as 200 | 500 | 503 | 504)
})

// Get agent dialog entries (with optional ?since=seq for incremental polling)
app.get("/api/containers/:id/agent/dialog", async (c) => {
  const id = c.req.param("id")
  const since = c.req.query("since")
  if (since !== undefined && !/^\d+$/.test(since)) {
    return c.json({ error: "Invalid since: expected a sequence number" }, 400)
  }
  const endpoint = since ? `/agent/dialog?since=${since}` : "/agent/dialog"
  const { data, status } = await proxyToSDK(id, endpoint)
  return c.json(data, status as 200 | 500 | 503 | 504)
})

// Get evaluation result (after agent finishes)
app.get("/api/containers/:id/result", async (c) => {
  const id = c.req.param("id")
  const { data, status } = await proxyToSDK(id, "/result")
  return c.json(data, status as 200 | 500 | 503 | 504)
})

// Get the reference patch, from the host: the daemon serves it only on its
// admin socket inside the container.
app.get("/api/containers/:id/reference/patch", async (c) => {
  const container = await resolveContainer(c.req.param("id"))
  if (!container) {
    return c.json({ error: "Container not found" }, 404)
  }
  const diff = readReferencePatch(container.labels, LOCAL_TASKS_PATH)
  return c.json({ diff: diff ?? "" })
})

// =============================================================================
// OpenCode Routes - Debug assistant SDK integration
// =============================================================================

// Health check for OpenCode server
app.get("/api/containers/:id/opencode/health", async (c) => {
  const id = c.req.param("id")
  const result = await checkOpenCodeHealth(id)
  return c.json(result)
})

// Create new OpenCode session
app.post("/api/containers/:id/opencode/sessions", async (c) => {
  const id = c.req.param("id")
  const body = await c.req.json()
  const { title, workingDir, apiKey } = body as {
    title?: string
    workingDir?: string
    apiKey?: string
  }

  const { data, status } = await createOpenCodeSession(
    id,
    title,
    workingDir,
    apiKey
  )
  return c.json(data, status as 200 | 400 | 500 | 503)
})

// List all sessions for a container
app.get("/api/containers/:id/opencode/sessions", async (c) => {
  const id = c.req.param("id")
  const directory = c.req.query("directory") // Optional working directory
  const { data, status } = await listOpenCodeSessions(id, directory)
  return c.json(data, status as 200 | 400 | 500 | 503)
})

// Get session details
app.get("/api/containers/:id/opencode/sessions/:sessionId", async (c) => {
  const id = c.req.param("id")
  const sessionId = c.req.param("sessionId")
  const { data, status } = await getOpenCodeSession(id, sessionId)
  return c.json(data, status as 200 | 404 | 500 | 503)
})

// Delete session
app.delete("/api/containers/:id/opencode/sessions/:sessionId", async (c) => {
  const id = c.req.param("id")
  const sessionId = c.req.param("sessionId")
  const { data, status } = await deleteOpenCodeSession(id, sessionId)
  return c.json(data, status as 200 | 404 | 500 | 503)
})

// Get messages in session
app.get(
  "/api/containers/:id/opencode/sessions/:sessionId/messages",
  async (c) => {
    const id = c.req.param("id")
    const sessionId = c.req.param("sessionId")
    const { data, status } = await getOpenCodeMessages(id, sessionId)
    return c.json(data, status as 200 | 404 | 500 | 503)
  }
)

// Send message to session
app.post(
  "/api/containers/:id/opencode/sessions/:sessionId/messages",
  async (c) => {
    const id = c.req.param("id")
    const sessionId = c.req.param("sessionId")
    const body = await c.req.json()
    const { message, directory } = body as {
      message: string
      directory?: string
    }

    console.log(
      `[Route] POST message to session ${sessionId}, directory: ${directory || "not provided"}`
    )

    const { data, status } = await sendOpenCodeMessage(
      id,
      sessionId,
      message,
      directory
    )
    return c.json(data, status as 200 | 400 | 404 | 500 | 503)
  }
)

// Reply to permission request
app.post(
  "/api/containers/:id/opencode/sessions/:sessionId/permissions/:permissionId",
  async (c) => {
    const id = c.req.param("id")
    const sessionId = c.req.param("sessionId")
    const permissionId = c.req.param("permissionId")
    const body = await c.req.json()
    const { allow } = body as { allow: boolean }

    console.log(`[Route] POST permission reply ${permissionId}: allow=${allow}`)

    const { data, status } = await replyOpenCodePermission(
      id,
      sessionId,
      permissionId,
      allow
    )
    return c.json(data, status as 200 | 400 | 404 | 500 | 503)
  }
)

// =============================================================================
// Launch Routes - Task launcher for SSEBench
// =============================================================================

// Get available tasks (local, or remote from the task catalog)
app.get("/api/launch/tasks", async (c) => {
  const source =
    c.req.query("source") || (isCatalogConfigured() ? "remote" : "local")

  try {
    if (source === "local") {
      const tasks = getLocalTasks()
      return c.json({ tasks })
    } else {
      if (!isCatalogConfigured()) {
        return c.json({ error: CATALOG_NOT_CONFIGURED, tasks: [] }, 503)
      }
      const tasks = await getRemoteTasks()
      return c.json({ tasks })
    }
  } catch (error) {
    console.error("Failed to fetch tasks:", error)
    return c.json({ error: "Failed to fetch tasks", tasks: [] }, 500)
  }
})

// Get available models
app.get("/api/launch/models", (c) => {
  const models = getModels()
  return c.json({ models })
})

// Get available agents
app.get("/api/launch/agents", (c) => {
  const agents = getAgents()
  return c.json({ agents })
})

// Which task sources are available
app.get("/api/launch/config", (c) => {
  return c.json({
    hasLocalBenchmarks: hasLocalBenchmarks(),
    catalogConfigured: isCatalogConfigured(),
    modes: ["sandbox", "sidecar"],
  })
})

// Launch a new task (supports multiple concurrent launches)
app.post("/api/launch", async (c) => {
  try {
    const body = await c.req.json().catch(() => null)
    const validation = validateLaunchConfig(body)
    if (!validation.ok) {
      return c.json({ error: validation.error }, 400)
    }

    const status = await launchTask(validation.config)
    return c.json(status)
  } catch (error) {
    console.error("Launch failed:", error)
    return c.json(
      { error: error instanceof Error ? error.message : "Launch failed" },
      500
    )
  }
})

// Get launch status — single launch by ?id= or all launches
app.get("/api/launch/status", (c) => {
  const id = c.req.query("id")

  if (id) {
    const status = getLaunchStatus(id)
    if (!status) {
      return c.json({ status: null })
    }
    return c.json(status)
  }

  // Return all launch statuses
  const statuses = getAllLaunchStatuses()
  return c.json({ launches: statuses })
})

// Get launch output logs for a specific launch (requires ?id=)
app.get("/api/launch/logs", (c) => {
  const id = c.req.query("id")
  if (!id) {
    return c.json({ error: "Missing required query parameter: id" }, 400)
  }
  return c.json({ logs: getLaunchOutput(id) })
})

// Cancel a specific launch (requires launch_id in body)
app.post("/api/launch/cancel", async (c) => {
  const body = await c.req.json<{ launch_id?: string }>()
  if (!body.launch_id) {
    return c.json({ error: "Missing required field: launch_id" }, 400)
  }
  const cancelled = cancelLaunch(body.launch_id)
  return c.json({ cancelled })
})

// Clear a specific launch entry, or all launches if no launch_id
app.post("/api/launch/clear", async (c) => {
  const body = await c.req.json<{ launch_id?: string }>().catch(() => ({}))
  const launchId = (body as { launch_id?: string }).launch_id

  if (launchId) {
    clearLaunchEntry(launchId)
  } else {
    clearAllLaunches()
  }
  return c.json({ cleared: true })
})

// =============================================================================
// Static File Serving (Production)
// =============================================================================

const distPath = "./dist"
if (existsSync(distPath)) {
  console.log(`[Static] Serving static files from ${distPath}`)

  // Serve static assets (JS, CSS, images, etc.)
  app.use("/*", serveStatic({ root: distPath }))

  // SPA fallback - serve index.html for client-side routes
  app.get("*", serveStatic({ root: distPath, path: "/index.html" }))
}

// Start server using Bun.serve()
const PORT = process.env.PORT ? parseInt(process.env.PORT) : 3001

// Store server reference for WebSocket upgrades
let server: Server<WSData>

/** Container ID segment of WebSocket routes (see isContainerId) */
const WS_CONTAINER_ID = "([a-f0-9]{12,64})"
const TERMINAL_WS_PATH = /^\/api\/pty(-debug)?\//

export default {
  port: PORT,
  hostname: security.host,

  // Main request handler
  fetch(request: Request, srv: Server<WSData>): Response | Promise<Response> {
    server = srv
    const url = new URL(request.url)

    // WebSocket upgrades are handled here, outside Hono, so they get the
    // same checks as the /api routes. Everything else goes to Hono.
    const upgradeHeaders = webSocketResponseHeaders(request)
    if (request.headers.get("upgrade")?.toLowerCase() === "websocket") {
      console.log(`[WS] Upgrade request for: ${url.pathname}`)

      const rejection = checkApiRequest(request, security)
      if (rejection) {
        console.warn(`[Auth] ${rejection.status} WS ${url.pathname}`)
        return rejection
      }
      if (!security.terminalEnabled && TERMINAL_WS_PATH.test(url.pathname)) {
        return Response.json(
          { error: "Terminal is disabled on this server" },
          { status: 403 }
        )
      }
    }

    // Handle WebSocket upgrade for PTY connections
    // Route: /api/pty/:containerId
    const ptyMatch = url.pathname.match(
      new RegExp(`^/api/pty/${WS_CONTAINER_ID}$`)
    )
    if (ptyMatch && request.headers.get("upgrade") === "websocket") {
      const containerId = ptyMatch[1]

      // Upgrade to WebSocket
      const success = server.upgrade(request, {
        data: { containerId, type: "bash" } satisfies WSData,
        headers: upgradeHeaders,
      })

      if (success) {
        // Return undefined to indicate upgrade was handled
        // Bun expects this for successful upgrades
        return new Response(null, { status: 101 })
      }

      return new Response("WebSocket upgrade failed", { status: 500 })
    }

    // Handle WebSocket upgrade for Debug PTY connections (OpenCode)
    // Route: /api/pty-debug/:containerId?message=...
    const ptyDebugMatch = url.pathname.match(
      new RegExp(`^/api/pty-debug/${WS_CONTAINER_ID}$`)
    )
    if (ptyDebugMatch && request.headers.get("upgrade") === "websocket") {
      const containerId = ptyDebugMatch[1]

      // Extract initial message from query parameter
      const initialMessage = url.searchParams.get("message") || undefined

      // Upgrade to WebSocket with debug type
      const success = server.upgrade(request, {
        data: { containerId, type: "debug", initialMessage } satisfies WSData,
        headers: upgradeHeaders,
      })

      if (success) {
        return new Response(null, { status: 101 })
      }

      return new Response("WebSocket upgrade failed", { status: 500 })
    }

    // Handle WebSocket upgrade for Launch (unified: status + logs)
    // Route: /api/launch/ws
    if (
      url.pathname === "/api/launch/ws" &&
      request.headers.get("upgrade") === "websocket"
    ) {
      console.log("[WS] Launch upgrade request")
      const success = server.upgrade(request, {
        data: { type: "launch" } satisfies WSData,
        headers: upgradeHeaders,
      })

      if (success) {
        return new Response(null, { status: 101 })
      }

      return new Response("WebSocket upgrade failed", { status: 500 })
    }

    // Handle WebSocket upgrade for Container Logs (docker logs -f)
    // Route: /api/containers/:id/logs-ws
    const containerLogsMatch = url.pathname.match(
      new RegExp(`^/api/containers/${WS_CONTAINER_ID}/logs-ws$`)
    )
    if (containerLogsMatch && request.headers.get("upgrade") === "websocket") {
      const containerId = containerLogsMatch[1]
      console.log(`[WS] Container logs upgrade request for: ${containerId}`)

      const success = server.upgrade(request, {
        data: { containerId, type: "container-logs" } satisfies WSData,
        headers: upgradeHeaders,
      })

      if (success) {
        return new Response(null, { status: 101 })
      }

      return new Response("WebSocket upgrade failed", { status: 500 })
    }

    // Handle WebSocket upgrade for OpenCode Events
    // Route: /api/containers/:containerId/opencode/events-ws?sessionId=...&directory=...
    const opencodeEventsMatch = url.pathname.match(
      new RegExp(`^/api/containers/${WS_CONTAINER_ID}/opencode/events-ws$`)
    )
    if (opencodeEventsMatch && request.headers.get("upgrade") === "websocket") {
      const containerId = opencodeEventsMatch[1]
      const sessionId = url.searchParams.get("sessionId") || undefined
      const directory = url.searchParams.get("directory") || undefined

      console.log(
        `[WS] OpenCode events upgrade request - container: ${containerId}, session: ${sessionId}, directory: ${directory}`
      )

      const success = server.upgrade(request, {
        data: {
          containerId,
          type: "opencode-events",
          sessionId,
          directory,
        } satisfies WSData,
        headers: upgradeHeaders,
      })

      if (success) {
        console.log("[WS] OpenCode events upgrade successful")
        return new Response(null, { status: 101 })
      }

      console.error("[WS] OpenCode events upgrade failed")
      return new Response("WebSocket upgrade failed", { status: 500 })
    }

    // Handle WebSocket upgrade for SDK Data Streaming
    // Route: /api/containers/:id/sdk-ws
    const sdkWsMatch = url.pathname.match(
      new RegExp(`^/api/containers/${WS_CONTAINER_ID}/sdk-ws$`)
    )
    if (sdkWsMatch && request.headers.get("upgrade") === "websocket") {
      const containerId = sdkWsMatch[1]
      console.log(`[WS] SDK WebSocket upgrade request for: ${containerId}`)

      const success = server.upgrade(request, {
        data: { containerId, type: "sdk" } satisfies WSData,
        headers: upgradeHeaders,
      })

      if (success) {
        console.log("[WS] SDK WebSocket upgrade successful")
        return new Response(null, { status: 101 })
      }

      console.error("[WS] SDK WebSocket upgrade failed")
      return new Response("WebSocket upgrade failed", { status: 500 })
    }

    // Handle all other routes with Hono
    return app.fetch(request, srv)
  },

  // WebSocket handlers for PTY connections
  websocket: {
    // Called when a WebSocket connection is opened
    async open(ws: ServerWebSocket<WSData>) {
      const { containerId, type, initialMessage, sessionId, directory } =
        ws.data
      console.log(
        `[WS] Connection opened for container: ${containerId}, type: ${type || "bash"}, hasMessage: ${!!initialMessage}`
      )

      // Handle unified launch WebSocket (status + logs)
      if (type === "launch") {
        console.log("[WS] Launch subscriber connected")
        subscribeToLaunch(ws)
        return
      }

      // Handle container logs WebSocket (docker logs -f)
      if (type === "container-logs") {
        console.log(
          `[WS] Container logs subscriber connected for: ${containerId}`
        )
        if (containerId) {
          startContainerLogStream(containerId, ws)
        } else {
          console.error("[WS] No containerId provided for container-logs")
          ws.close()
        }
        return
      }

      // Handle SDK WebSocket (unified SDK data streaming)
      if (type === "sdk") {
        console.log(
          `[WS] SDK WebSocket subscriber connected for: ${containerId}`
        )
        if (containerId) {
          await startSDKConnection(containerId, ws)
        } else {
          console.error("[WS] No containerId provided for SDK WebSocket")
          ws.close()
        }
        return
      }

      // Handle OpenCode events WebSocket
      if (type === "opencode-events") {
        console.log(
          `[WS] OpenCode events subscriber connected - container: ${containerId}, session: ${sessionId}, directory: ${directory}`
        )

        // Send connection confirmation immediately
        try {
          ws.send(
            JSON.stringify({
              type: "connection",
              data: { status: "connected" },
            })
          )
          console.log("[WS] Connection confirmation sent")
        } catch (error) {
          console.error("[WS] Failed to send connection confirmation:", error)
        }

        // Start streaming events in the background
        setImmediate(async () => {
          try {
            console.log(
              `[WS] Calling streamSessionEvents for container: ${containerId}`
            )

            const eventStream = await streamSessionEvents(
              containerId!,
              directory,
              sessionId
            )

            if (!eventStream) {
              console.error(
                "[WS] streamSessionEvents returned null - OpenCode may not be running"
              )
              if (ws.readyState === 1) {
                ws.send(
                  JSON.stringify({
                    type: "error",
                    data: {
                      error:
                        "Failed to connect to OpenCode event stream - OpenCode may not be running",
                    },
                  })
                )
              }
              return
            }

            console.log(
              "[WS] OpenCode event stream created successfully, starting to stream events"
            )

            // Stream events to client
            let eventCount = 0
            for await (const event of eventStream) {
              // Check if connection is still open
              if (ws.readyState !== 1) {
                console.log(
                  `[WS] Connection closed after ${eventCount} events, stopping event stream`
                )
                break
              }

              eventCount++
              console.log(`[WS] Streaming event #${eventCount}: ${event.type}`)

              try {
                ws.send(
                  JSON.stringify({
                    type: event.type || "event",
                    data: event,
                  })
                )
              } catch (sendError) {
                console.error("[WS] Failed to send event:", sendError)
                break
              }
            }

            console.log(
              `[WS] OpenCode event stream ended after ${eventCount} events`
            )
          } catch (error) {
            console.error("[WS] OpenCode event stream error:", error)
            if (ws.readyState === 1) {
              try {
                ws.send(
                  JSON.stringify({
                    type: "error",
                    data: { error: String(error) },
                  })
                )
              } catch (sendError) {
                console.error("[WS] Failed to send error event:", sendError)
              }
            }
          }
        })

        return
      }

      // Ensure containerId exists for PTY connections
      if (!containerId) {
        console.error("[WS] No containerId provided for PTY connection")
        ws.close()
        return
      }

      // Handle debug terminal (OpenCode)
      if (type === "debug") {
        // The message is one argument to opencode, never shell text
        const command = initialMessage
          ? ["opencode", "run", initialMessage]
          : ["opencode"]
        if (initialMessage) {
          console.log(
            `[WS] Starting OpenCode with message: ${initialMessage.substring(0, 100)}...`
          )
        }

        let sourceDir = "/src"
        try {
          const { data } = await proxyToSDK(containerId, "/project")
          const source = (data as { source?: unknown } | null)?.source
          if (typeof source === "string" && source.startsWith("/")) {
            sourceDir = source
          }
        } catch (error) {
          // Fall back to /src if we can't get project info
          console.error(
            `[WS] Failed to get source directory for debug session:`,
            error
          )
        }
        console.log(`[WS] Debug session - source directory: ${sourceDir}`)

        await createPTYSession(containerId, ws, 80, 24, command, sourceDir)
      } else {
        // Regular bash terminal
        await createPTYSession(containerId, ws, 80, 24)
      }
    },

    // Called when a message is received from the client
    message(ws: ServerWebSocket<WSData>, message: string | Buffer) {
      handleMessage(ws, message)
    },

    // Called when the WebSocket connection is closed
    close(ws: ServerWebSocket<WSData>) {
      const { containerId, type } = ws.data

      // Handle unified launch unsubscribe
      if (type === "launch") {
        console.log("[WS] Launch subscriber disconnected")
        unsubscribeFromLaunch(ws)
        return
      }

      // Handle container logs unsubscribe
      if (type === "container-logs") {
        console.log(
          `[WS] Container logs subscriber disconnected for: ${containerId}`
        )
        stopContainerLogStream(ws)
        return
      }

      // Handle SDK WebSocket unsubscribe
      if (type === "sdk") {
        console.log(
          `[WS] SDK WebSocket subscriber disconnected for: ${containerId}`
        )
        if (containerId) {
          stopSDKConnection(containerId, ws)
        }
        return
      }

      console.log(`[WS] Connection closed for container: ${containerId}`)
      handleClose(ws)
    },

    // Called on WebSocket error
    error(ws: ServerWebSocket<WSData>, error: Error) {
      console.error(`[WS] Error for container ${ws.data.containerId}:`, error)
    },
  },
}

const displayHost = security.host.includes(":")
  ? `[${security.host}]`
  : security.host
console.log(`🚀 SSEBench WebUI Server running on http://${displayHost}:${PORT}`)
console.log(
  `   Auth: ${security.token ? "bearer token required" : "none (loopback only)"}`
)
console.log(`   Terminal: ${security.terminalEnabled ? "enabled" : "disabled"}`)
if (security.corsOrigins.size > 0) {
  console.log(`   CORS origins: ${[...security.corsOrigins].join(", ")}`)
}
console.log(``)
console.log(`   Container Endpoints:`)
console.log(`   - GET  /api/health                       Health check`)
console.log(`   - GET  /api/containers                   List all containers`)
console.log(`   - GET  /api/containers/:id               Get container info`)
console.log(
  `   - GET  /api/containers/:id/project       Get task metadata (SDK)`
)
console.log(`   - GET  /api/containers/:id/diff          Get code diff (SDK)`)
console.log(
  `   - GET  /api/containers/:id/files         Get modified files (SDK)`
)
console.log(`   - GET  /api/containers/:id/sdk/health    SDK health check`)
console.log(`   - GET  /api/containers/:id/sdk/version   SDK version info`)
console.log(
  `   - GET  /api/containers/:id/agent/dialog  Agent dialog entries (SDK)`
)
console.log(`   - WS   /api/pty/:containerId             Terminal WebSocket`)
console.log(``)
console.log(`   Launch Endpoints:`)
console.log(`   - GET  /api/launch/tasks?source=         Get available tasks`)
console.log(`   - GET  /api/launch/models                Get available models`)
console.log(`   - GET  /api/launch/agents                Get available agents`)
console.log(
  `   - GET  /api/launch/config                Get launch configuration`
)
console.log(`   - POST /api/launch                       Launch a new task`)
console.log(
  `   - GET  /api/launch/status                Get current launch status`
)
console.log(
  `   - GET  /api/launch/logs                  Get launch output logs`
)
console.log(`   - POST /api/launch/cancel                Cancel current launch`)
console.log(``)
if (CATALOG) {
  console.log(`   Task catalog: ${CATALOG.location}`)
  if (CATALOG.deprecated) {
    console.log(`   SSEBENCH_CATALOG_URL is deprecated; set SSEBENCH_CATALOG`)
  }
} else {
  console.log(`   ${CATALOG_NOT_CONFIGURED}; listing local tasks only`)
}
console.log(``)
console.log(`   Press Ctrl+C to shut down gracefully`)

// =============================================================================
// Graceful Shutdown Handlers
// =============================================================================

/**
 * Handle shutdown signals to clean up PTY sessions and OpenCode processes
 */
async function handleShutdown(signal: string): Promise<void> {
  console.log(`\n[Server] Received ${signal}, shutting down gracefully...`)

  // Shutdown PTY sessions
  shutdownAllSessions()

  // Shutdown container log streams
  shutdownAllLogStreams()

  // Shutdown SDK WebSocket connections
  shutdownAllSDKConnections()

  // Shutdown OpenCode processes
  await shutdownOpenCode()

  process.exit(0)
}

// Register signal handlers
process.on("SIGINT", () => handleShutdown("SIGINT"))
process.on("SIGTERM", () => handleShutdown("SIGTERM"))
