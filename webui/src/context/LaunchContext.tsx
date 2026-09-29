/**
 * Launch Context — Multi-launch state management
 *
 * Tracks multiple concurrent launches via a single WebSocket connection.
 * Each launch has its own independent status and log stream, keyed by launch_id.
 *
 * WebSocket message formats from backend:
 *   { type: "status",  launch_id: string, data: LaunchStatus }
 *   { type: "log",     launch_id: string, data: string }
 *   { type: "cleared", launch_id: string }
 */

import { ReactNode, useState, useEffect, useRef, useCallback } from "react"
import {
  openWebSocket,
  cancelLaunch as apiCancelLaunch,
  clearLaunchEntry as apiClearLaunchEntry,
  clearAllLaunches as apiClearAllLaunches,
} from "../lib/api"
import type { LaunchStatus } from "../types/launch"
import {
  LaunchContext,
  type LaunchContextValue,
  type LaunchEntry,
} from "./useLaunchContext"

// =============================================================================
// Provider
// =============================================================================

interface LaunchProviderProps {
  children: ReactNode
}

export function LaunchProvider({ children }: LaunchProviderProps) {
  const [launches, setLaunches] = useState<Map<string, LaunchEntry>>(new Map())
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // IDs we've decided to dismiss — all future WS messages for these are ignored.
  // This prevents races where a stale WS broadcast re-adds an entry we already cleared.
  const dismissedIdsRef = useRef<Set<string>>(new Set())

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return
    }

    const wsPath = "/api/launch/ws"
    console.log("[Launch] Connecting to:", wsPath)

    const ws = openWebSocket(wsPath)
    wsRef.current = ws

    ws.onopen = () => {
      console.log("[Launch] WebSocket connected")
      setIsConnected(true)
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        const launchId: string | undefined = msg.launch_id

        // Ignore messages for launches we've already dismissed
        if (launchId && dismissedIdsRef.current.has(launchId)) {
          return
        }

        if (msg.type === "status" && launchId) {
          setLaunches((prev) => {
            // Double-check inside functional update (dismissedIds may have been
            // added between the outer check and when React processes this update)
            if (dismissedIdsRef.current.has(launchId)) return prev
            const next = new Map(prev)
            const existing = next.get(launchId)
            next.set(launchId, {
              status: msg.data as LaunchStatus,
              logs: existing?.logs ?? [],
            })
            return next
          })
        } else if (msg.type === "log" && launchId) {
          setLaunches((prev) => {
            if (dismissedIdsRef.current.has(launchId)) return prev
            const next = new Map(prev)
            const existing = next.get(launchId)
            if (existing) {
              next.set(launchId, {
                ...existing,
                logs: [...existing.logs, msg.data as string],
              })
            } else {
              // Log arrived before status — create placeholder
              next.set(launchId, {
                status: {
                  launch_id: launchId,
                  status: "launching",
                  command: "",
                  taskId: "",
                  startTime: new Date().toISOString(),
                },
                logs: [msg.data as string],
              })
            }
            return next
          })
        } else if (msg.type === "cleared" && launchId) {
          setLaunches((prev) => {
            const next = new Map(prev)
            next.delete(launchId)
            return next
          })
        }
      } catch (err) {
        console.error("[Launch] Failed to parse message:", err)
      }
    }

    ws.onerror = () => {
      console.error("[Launch] WebSocket error")
    }

    ws.onclose = () => {
      console.log("[Launch] WebSocket closed")
      setIsConnected(false)
      wsRef.current = null

      // Reconnect after delay
      reconnectTimeoutRef.current = setTimeout(() => {
        console.log("[Launch] Reconnecting...")
        connect()
      }, 5000)
    }
  }, [])

  // Initial connection
  useEffect(() => {
    connect()

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])

  // Cancel a specific launch
  const cancel = useCallback(async (launchId: string): Promise<boolean> => {
    try {
      return await apiCancelLaunch(launchId)
    } catch (err) {
      console.error("[Launch] Failed to cancel:", err)
      return false
    }
  }, [])

  // Clear a specific launch — dismiss immediately so WS can't re-add it
  const clear = useCallback(async (launchId: string): Promise<void> => {
    // 1. Dismiss: ignore all future WS messages for this launch
    dismissedIdsRef.current.add(launchId)

    // 2. Optimistic local removal (immediate, before API round-trip)
    setLaunches((prev) => {
      const next = new Map(prev)
      next.delete(launchId)
      return next
    })

    // 3. Tell the server to clean up
    try {
      await apiClearLaunchEntry(launchId)
    } catch (err) {
      console.error("[Launch] Failed to clear on server:", err)
    }
  }, [])

  // Clear all launches
  const clearAll = useCallback(async (): Promise<void> => {
    // Dismiss all current IDs
    setLaunches((prev) => {
      for (const id of prev.keys()) {
        dismissedIdsRef.current.add(id)
      }
      return new Map()
    })

    try {
      await apiClearAllLaunches()
    } catch (err) {
      console.error("[Launch] Failed to clear all on server:", err)
    }
  }, [])

  // Get a specific launch
  const getLaunch = useCallback(
    (launchId: string): LaunchEntry | undefined => {
      return launches.get(launchId)
    },
    [launches]
  )

  // Derived values
  const allLaunches = Array.from(launches.values())
  const hasActiveLaunches = allLaunches.some(
    (entry) => entry.status.status === "launching"
  )

  const contextValue: LaunchContextValue = {
    launches,
    allLaunches,
    hasActiveLaunches,
    isConnected,
    getLaunch,
    cancel,
    clear,
    clearAll,
  }

  return (
    <LaunchContext.Provider value={contextValue}>
      {children}
    </LaunchContext.Provider>
  )
}
