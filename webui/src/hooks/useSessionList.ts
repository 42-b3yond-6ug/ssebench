/**
 * useSessionList Hook
 *
 * Manages the list of OpenCode sessions for a container.
 * Provides session listing, refresh, and deletion capabilities.
 */

import { useState, useEffect, useCallback, useMemo, useRef } from "react"
import { OpenCodeClient } from "../lib/opencodeClient"
import type { OpenCodeSessionListItem } from "../types/opencode"

/**
 * Compare two session lists to see if they're different
 * This prevents unnecessary re-renders when polling
 */
function sessionsChanged(
  oldSessions: OpenCodeSessionListItem[],
  newSessions: OpenCodeSessionListItem[]
): boolean {
  if (oldSessions.length !== newSessions.length) return true

  // Compare session IDs and titles (most likely to change)
  for (let i = 0; i < oldSessions.length; i++) {
    if (
      oldSessions[i].id !== newSessions[i].id ||
      oldSessions[i].title !== newSessions[i].title
    ) {
      return true
    }
  }

  return false
}

interface UseSessionListOptions {
  containerId: string
  directory?: string // Working directory (source code folder)
  enabled?: boolean
  refreshInterval?: number
}

interface UseSessionListResult {
  sessions: OpenCodeSessionListItem[]
  isLoading: boolean
  error: string | null
  refresh: () => Promise<void>
  deleteSession: (sessionId: string) => Promise<void>
}

/**
 * Hook to manage OpenCode session list
 */
export function useSessionList({
  containerId,
  directory,
  enabled = true,
  refreshInterval = 5000,
}: UseSessionListOptions): UseSessionListResult {
  const [sessions, setSessions] = useState<OpenCodeSessionListItem[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const isInitialLoad = useRef(true)

  const client = useMemo(() => new OpenCodeClient(containerId), [containerId])

  const refresh = useCallback(
    async (silent = false) => {
      if (!enabled) return

      // Only show loading spinner on initial load, not during auto-refresh
      if (!silent && isInitialLoad.current) {
        setIsLoading(true)
      }

      setError(null)

      try {
        const sessionList = await client.listSessions(directory)

        // Only update state if sessions actually changed (prevents flicker)
        setSessions((prevSessions) => {
          if (sessionsChanged(prevSessions, sessionList)) {
            return sessionList
          }
          return prevSessions
        })
      } catch (err) {
        const errorMessage =
          err instanceof Error ? err.message : "Failed to load sessions"
        setError(errorMessage)
        console.error("[SessionList] Error:", errorMessage)
      } finally {
        // Turn off loading spinner after initial load completes
        if (!silent && isInitialLoad.current) {
          setIsLoading(false)
          isInitialLoad.current = false
        }
      }
    },
    [client, directory, enabled]
  )

  // Initial load
  useEffect(() => {
    refresh()
  }, [refresh])

  // Auto-refresh interval (silent updates in background)
  useEffect(() => {
    if (!enabled || !refreshInterval) return

    const interval = setInterval(() => {
      refresh(true) // Silent refresh - no loading spinner
    }, refreshInterval)
    return () => clearInterval(interval)
  }, [refresh, enabled, refreshInterval])

  const deleteSession = useCallback(
    async (sessionId: string) => {
      try {
        await client.deleteSession(sessionId)
        // Refresh list after deletion (not silent - user action)
        await refresh(false)
      } catch (err) {
        const errorMessage =
          err instanceof Error ? err.message : "Failed to delete session"
        console.error("[SessionList] Delete error:", errorMessage)
        throw err
      }
    },
    [client, refresh]
  )

  return {
    sessions,
    isLoading,
    error,
    refresh,
    deleteSession,
  }
}
