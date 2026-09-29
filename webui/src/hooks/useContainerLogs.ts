/**
 * Hook for subscribing to container logs via WebSocket
 *
 * Streams logs from `docker logs -f <containerId>` through the backend.
 * Unlike LaunchContext logs (which capture Python subprocess output),
 * this streams logs directly from the Docker container.
 */

import { useState, useEffect, useRef, useCallback } from "react"
import { getWsBaseUrl } from "../lib/api"

interface UseContainerLogsReturn {
  logs: string[]
  isConnected: boolean
  error: string | null
  clearLogs: () => void
}

export function useContainerLogs(
  containerId: string | null
): UseContainerLogsReturn {
  const [logs, setLogs] = useState<string[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  // Clear logs when container changes
  useEffect(() => {
    setLogs([])
    setError(null)
  }, [containerId])

  useEffect(() => {
    // Don't connect if no container ID
    if (!containerId) {
      setIsConnected(false)
      return
    }

    const wsUrl = `${getWsBaseUrl()}/api/containers/${containerId}/logs-ws`
    console.log("[useContainerLogs] Connecting to:", wsUrl)

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      console.log("[useContainerLogs] WebSocket connected")
      setIsConnected(true)
      setError(null)
    }

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)

        if (message.type === "log") {
          setLogs((prev) => [...prev, message.data])
        } else if (message.type === "error") {
          console.error("[useContainerLogs] Server error:", message.data?.error)
          setError(message.data?.error)
        } else if (message.type === "end") {
          console.log(
            "[useContainerLogs] Log stream ended, exit code:",
            message.data?.exitCode
          )
        }
      } catch (err) {
        console.error("[useContainerLogs] Failed to parse message:", err)
      }
    }

    ws.onerror = (err) => {
      console.error("[useContainerLogs] WebSocket error:", err)
      setError("WebSocket connection error")
    }

    ws.onclose = () => {
      console.log("[useContainerLogs] WebSocket disconnected")
      setIsConnected(false)
    }

    return () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close()
      }
    }
  }, [containerId])

  const clearLogs = useCallback(() => {
    setLogs([])
  }, [])

  return { logs, isConnected, error, clearLogs }
}
