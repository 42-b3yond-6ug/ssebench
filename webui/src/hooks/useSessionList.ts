/**
 * useSessionList Hook
 *
 * Manages the list of OpenCode sessions for a container.
 * Provides session listing, refresh, and deletion capabilities.
 */

import { useState, useEffect, useCallback, useMemo } from "react"
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
  // Only the first load shows a spinner, not the auto-refresh
  const [isLoading, setIsLoading] = useState(enabled)
  const [error, setError] = useState<string | null>(null)

  const client = useMemo(() => new OpenCodeClient(containerId), [containerId])

  const refresh = useCallback((): Promise<void> => {
    if (!enabled) return Promise.resolve()
    return client
      .listSessions(directory)
      .then(
        (sessionList) => {
          setError(null)
          // Only update state if sessions actually changed (prevents flicker)
          setSessions((prevSessions) =>
            sessionsChanged(prevSessions, sessionList)
              ? sessionList
              : prevSessions
          )
        },
        (err: unknown) => {
          const errorMessage =
            err instanceof Error ? err.message : "Failed to load sessions"
          setError(errorMessage)
          console.error("[SessionList] Error:", errorMessage)
        }
      )
      .finally(() => setIsLoading(false))
  }, [client, directory, enabled])

  // Initial load
  useEffect(() => {
    refresh()
  }, [refresh])

  // Auto-refresh interval (silent updates in background)
  useEffect(() => {
    if (!enabled || !refreshInterval) return

    const interval = setInterval(() => {
      refresh()
    }, refreshInterval)
    return () => clearInterval(interval)
  }, [refresh, enabled, refreshInterval])

  const deleteSession = useCallback(
    async (sessionId: string) => {
      try {
        await client.deleteSession(sessionId)
        await refresh()
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
