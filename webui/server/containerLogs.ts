/**
 * Container Logs Module - Stream a run's container output via WebSocket
 *
 * Provides real-time log streaming through `ssebench runs logs --follow`,
 * which reads the container's output from whatever backend runs it. Unlike
 * the launch logs (which capture Python subprocess output), this is the
 * container's own. A run whose container is gone shows the logs its run
 * directory kept.
 */

import { spawn, type Subprocess } from "bun"
import type { ServerWebSocket } from "bun"
import { readLogText } from "./pastRuns"
import { runnerCommand, runnerEnv } from "./runner"
import { resolveRun } from "./runs"
import { ssebenchPath } from "./config"

// Track active log streams per WebSocket connection
const activeStreams: Map<ServerWebSocket<unknown>, Subprocess> = new Map()

/**
 * Start streaming logs for a container to a WebSocket client
 *
 * @param containerId - the run's ID
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
    const run = await resolveRun(containerId)
    if (!run) {
      throw new Error(`Run ${containerId} not found`)
    }
    // The client may have gone away while the run was being resolved
    if (ws.readyState !== WebSocket.OPEN) return

    if (run.source === "results") {
      const text = run.resultsDir ? readLogText(run.resultsDir) : ""
      for (const line of text.split("\n")) {
        if (line.trim()) ws.send(JSON.stringify({ type: "log", data: line }))
      }
      ws.send(JSON.stringify({ type: "end", data: { exitCode: 0 } }))
      return
    }

    // Follow mode, with no limit on how much is read
    const proc = spawn({
      cmd: [...runnerCommand(), "runs", "logs", "--follow", run.id],
      cwd: ssebenchPath(),
      env: runnerEnv(),
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

    // Stream stderr: the CLI's own complaints
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
        `[containerLogs] logs exited with code ${exitCode} for ${containerId}`
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
