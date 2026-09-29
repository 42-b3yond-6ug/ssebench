/**
 * Unified SDK WebSocket Hook
 *
 * Provides all SDK data through a single WebSocket connection:
 * - Connection status and SDK readiness
 * - Project metadata
 * - Changed files and diff
 * - Agent dialog entries
 * - Evaluation result
 *
 * Replaces: useSDKData, useAgentDialog, useEvaluationResult
 */

import { useState, useEffect, useRef, useCallback } from "react"
import { openWebSocket } from "../lib/api"
import type {
  ProjectInfo,
  ChangedFile,
  DialogEntry,
  EvaluationResultResponse,
} from "../types/container"

// =============================================================================
// Types
// =============================================================================

type ConnectionStatus = "connecting" | "ready" | "error" | "disconnected"

interface SDKWebSocketState {
  // Connection state
  status: ConnectionStatus
  retryAttempt: number
  error: string | null
  sdkVersion: string | null

  // SDK data
  project: ProjectInfo | null
  files: ChangedFile[]
  diff: string
  dialogEntries: DialogEntry[]
  evaluationResult: EvaluationResultResponse | null

  // Computed properties
  isInitializing: boolean
  sdkReady: boolean
  isComplete: boolean
  totalAdditions: number
  totalDeletions: number
  latestDialogSeq: number
}

interface SDKWebSocketReturn extends SDKWebSocketState {
  /** Manually reconnect the WebSocket */
  reconnect: () => void
}

// =============================================================================
// Initial State
// =============================================================================

const initialState: SDKWebSocketState = {
  status: "disconnected",
  retryAttempt: 0,
  error: null,
  sdkVersion: null,
  project: null,
  files: [],
  diff: "",
  dialogEntries: [],
  evaluationResult: null,
  isInitializing: true,
  sdkReady: false,
  isComplete: false,
  totalAdditions: 0,
  totalDeletions: 0,
  latestDialogSeq: -1,
}

// =============================================================================
// Hook
// =============================================================================

export function useSDKWebSocket(
  containerId: string | null
): SDKWebSocketReturn {
  const [state, setState] = useState<SDKWebSocketState>(initialState)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptRef = useRef(0)

  // Reconnect function
  const reconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    reconnectAttemptRef.current = 0
    setState((s) => ({ ...s, status: "connecting", error: null }))
  }, [])

  useEffect(() => {
    if (!containerId) {
      setState(initialState)
      return
    }

    // Reset state for new container
    setState({
      ...initialState,
      status: "connecting",
      isInitializing: true,
    })

    const wsPath = `/api/containers/${containerId}/sdk-ws`
    console.log(`[useSDKWebSocket] Connecting to: ${wsPath}`)

    const ws = openWebSocket(wsPath)
    wsRef.current = ws

    ws.onopen = () => {
      console.log("[useSDKWebSocket] WebSocket connected")
      reconnectAttemptRef.current = 0
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)

        switch (msg.type) {
          case "status":
            if (msg.status === "connecting") {
              setState((s) => ({
                ...s,
                status: "connecting",
                retryAttempt: msg.retryAttempt || 0,
                isInitializing: true,
                sdkReady: false,
              }))
            } else if (msg.status === "ready") {
              setState((s) => ({
                ...s,
                status: "ready",
                retryAttempt: 0,
                isInitializing: false,
                sdkReady: true,
                sdkVersion: msg.sdkVersion || null,
                error: null,
              }))
            } else if (msg.status === "error") {
              setState((s) => ({
                ...s,
                status: "error",
                error: msg.error || "Unknown error",
                isInitializing: false,
                sdkReady: false,
              }))
            }
            break

          case "project":
            setState((s) => ({
              ...s,
              project: msg.data,
            }))
            break

          case "files":
            setState((s) => {
              const files = msg.files || []
              return {
                ...s,
                files,
                totalAdditions: files.reduce(
                  (sum: number, f: ChangedFile) => sum + f.additions,
                  0
                ),
                totalDeletions: files.reduce(
                  (sum: number, f: ChangedFile) => sum + f.deletions,
                  0
                ),
              }
            })
            break

          case "diff":
            setState((s) => ({
              ...s,
              diff: msg.diff || "",
            }))
            break

          case "dialog":
            setState((s) => {
              const newEntries = msg.entries || []
              const allEntries = [...s.dialogEntries, ...newEntries]

              // Check if session is complete
              const isComplete = allEntries.some((e) => e.type === "complete")

              return {
                ...s,
                dialogEntries: allEntries,
                latestDialogSeq: msg.lastSeq ?? s.latestDialogSeq,
                isComplete,
              }
            })
            break

          case "result":
            setState((s) => ({
              ...s,
              evaluationResult: msg.result,
            }))
            break

          case "error":
            console.error("[useSDKWebSocket] Server error:", msg.error)
            setState((s) => ({
              ...s,
              error: msg.error || "Server error",
            }))
            break

          default:
            console.warn("[useSDKWebSocket] Unknown message type:", msg.type)
        }
      } catch (error) {
        console.error("[useSDKWebSocket] Failed to parse message:", error)
      }
    }

    ws.onerror = (error) => {
      console.error("[useSDKWebSocket] WebSocket error:", error)
      setState((s) => ({
        ...s,
        error: "WebSocket connection error",
      }))
    }

    ws.onclose = (event) => {
      console.log(
        `[useSDKWebSocket] WebSocket closed: code=${event.code}, reason=${event.reason}`
      )
      wsRef.current = null

      setState((s) => ({
        ...s,
        status: "disconnected",
      }))

      // Auto-reconnect with backoff (only if not intentionally closed)
      if (event.code !== 1000 && reconnectAttemptRef.current < 5) {
        const delay = Math.min(1000 * Math.pow(2, reconnectAttemptRef.current), 30000)
        reconnectAttemptRef.current++
        console.log(
          `[useSDKWebSocket] Reconnecting in ${delay}ms (attempt ${reconnectAttemptRef.current})`
        )
        setTimeout(() => {
          if (containerId) {
            // Trigger re-render to reconnect
            setState((s) => ({ ...s, status: "connecting" }))
          }
        }, delay)
      }
    }

    return () => {
      console.log("[useSDKWebSocket] Cleaning up WebSocket")
      if (ws.readyState === WebSocket.OPEN) {
        ws.close(1000, "Component unmounted")
      }
      wsRef.current = null
    }
  }, [containerId])

  return {
    ...state,
    reconnect,
  }
}
