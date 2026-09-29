/**
 * Container Logs Module - Stream docker logs via WebSocket
 *
 * Provides real-time container log streaming using `docker logs -f`.
 * Unlike the launch logs (which capture Python subprocess output),
 * this streams logs directly from the Docker container.
 */

import { spawn, type Subprocess } from "bun"
import type { ServerWebSocket } from "bun"
import { resolveContainer } from "./docker"

// Track active log streams per WebSocket connection
const activeStreams: Map<ServerWebSocket<unknown>, Subprocess> = new Map()

/**
 * Start streaming logs for a container to a WebSocket client
 *
 * @param containerId - Docker container ID
 * @param ws - WebSocket connection to stream logs to
 */
export async function startContainerLogStream(
  containerId: string,
  ws: ServerWebSocket<unknown>
): Promise<void> {
  // Stop any existing stream for this connection
  stopContainerLogStream(ws)

  console.log(
    `[containerLogs] Starting log stream for container: ${containerId}`
  )

  try {
    const container = await resolveContainer(containerId)
    if (!container) {
      throw new Error(`Container ${containerId} not found`)
    }
    // The client may have gone away while the container was being resolved
    if (ws.readyState !== WebSocket.OPEN) return

    // Spawn docker logs with follow mode
    // No --tail limit to fetch ALL logs
    const proc = spawn({
      cmd: ["docker", "logs", "-f", container.id],
      stdout: "pipe",
      stderr: "pipe",
    })

    activeStreams.set(ws, proc)

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
            const lines = text.split("\n")

            for (const line of lines) {
              // Skip empty lines
              if (!line.trim()) continue

              try {
                ws.send(JSON.stringify({ type: "log", data: line }))
              } catch {
                // WebSocket closed, stop streaming
                console.log(
                  `[containerLogs] WebSocket closed for ${containerId}, stopping stream`
                )
                stopContainerLogStream(ws)
                return
              }
            }
          }
        } catch (error) {
          console.error(`[containerLogs] stdout stream error:`, error)
        }
      })()
    }

    // Stream stderr (docker logs outputs to stderr for container stderr)
    const stderr = proc.stderr
    if (stderr && typeof stderr !== "number") {
      const reader = stderr.getReader()
      ;(async () => {
        try {
          while (true) {
            const { done, value } = await reader.read()
            if (done) break

            const text = new TextDecoder().decode(value)
            const lines = text.split("\n")

            for (const line of lines) {
              // Skip empty lines
              if (!line.trim()) continue

              try {
                ws.send(JSON.stringify({ type: "log", data: line }))
              } catch {
                // WebSocket closed, stop streaming
                stopContainerLogStream(ws)
                return
              }
            }
          }
        } catch (error) {
          console.error(`[containerLogs] stderr stream error:`, error)
        }
      })()
    }

    // Monitor process exit
    proc.exited.then((exitCode) => {
      console.log(
        `[containerLogs] docker logs exited with code ${exitCode} for ${containerId}`
      )

      // Clean up
      if (activeStreams.get(ws) === proc) {
        activeStreams.delete(ws)
      }

      // Notify client that stream ended
      try {
        ws.send(JSON.stringify({ type: "end", data: { exitCode } }))
      } catch {
        // WebSocket already closed
      }
    })
  } catch (error) {
    console.error(`[containerLogs] Failed to start log stream:`, error)
    try {
      ws.send(
        JSON.stringify({
          type: "error",
          data: {
            error: error instanceof Error ? error.message : String(error),
          },
        })
      )
    } catch {
      // WebSocket closed
    }
  }
}

/**
 * Stop the log stream for a WebSocket connection
 */
export function stopContainerLogStream(ws: ServerWebSocket<unknown>): void {
  const proc = activeStreams.get(ws)
  if (proc) {
    console.log(`[containerLogs] Stopping log stream`)
    try {
      proc.kill()
    } catch {
      // Process already exited
    }
    activeStreams.delete(ws)
  }
}

/**
 * Clean up all active log streams (for graceful shutdown)
 */
export function shutdownAllLogStreams(): void {
  console.log(`[containerLogs] Shutting down ${activeStreams.size} log streams`)
  for (const [ws, proc] of activeStreams) {
    try {
      proc.kill()
    } catch {
      // Process already exited
    }
    activeStreams.delete(ws)
  }
}
