/**
 * SDK Data Context
 *
 * Provides shared SDK data to all child components via WebSocket:
 * - Project info, files, diff
 * - Agent dialog entries
 * - Evaluation result
 *
 * Uses unified WebSocket connection for real-time updates.
 * This prevents duplicate connections and ensures consistent data.
 */

import { ReactNode, useState, useEffect } from "react"
import { useSDKWebSocket } from "../hooks/useSDKWebSocket"
import { fetchReferencePatch } from "../lib/api"
import type { CompleteEntry } from "../types/container"
import { SDKDataContext, type SDKDataContextValue } from "./useSDKDataContext"

// =============================================================================
// Provider
// =============================================================================

interface SDKDataProviderProps {
  containerId: string
  children: ReactNode
}

/**
 * Provider component that manages SDK WebSocket connection and shares data.
 * Must be used with a valid containerId.
 */
export function SDKDataProvider({
  containerId,
  children,
}: SDKDataProviderProps) {
  // Use unified WebSocket hook
  const sdk = useSDKWebSocket(containerId)

  // Ground truth patch (fetched separately, only once when SDK is ready)
  const [groundTruthPatch, setGroundTruthPatch] = useState<string | null>(null)
  const [groundTruthFetched, setGroundTruthFetched] = useState(false)

  // Fetch ground truth when SDK becomes ready
  useEffect(() => {
    if (sdk.sdkReady && !groundTruthFetched) {
      setGroundTruthFetched(true)
      fetchReferencePatch(containerId)
        .then((data) => {
          if (data.diff && data.diff.trim()) {
            setGroundTruthPatch(data.diff)
          }
        })
        .catch((err) => {
          console.warn("Failed to fetch ground truth patch:", err)
        })
    }
  }, [containerId, sdk.sdkReady, groundTruthFetched])

  // Reset ground truth when container changes
  useEffect(() => {
    setGroundTruthPatch(null)
    setGroundTruthFetched(false)
  }, [containerId])

  // Find completion entry if exists
  const completion =
    sdk.dialogEntries.find((e): e is CompleteEntry => e.type === "complete") ??
    null

  // Build context value
  const contextValue: SDKDataContextValue = {
    // Connection state
    isInitializing: sdk.isInitializing,
    sdkReady: sdk.sdkReady,
    retryAttempt: sdk.retryAttempt,
    error: sdk.error,
    sdkVersion: sdk.sdkVersion,

    // Project data
    project: sdk.project,
    files: sdk.files,
    diff: sdk.diff,
    totalAdditions: sdk.totalAdditions,
    totalDeletions: sdk.totalDeletions,

    // Agent dialog
    dialogEntries: sdk.dialogEntries,
    latestDialogSeq: sdk.latestDialogSeq,
    isComplete: sdk.isComplete,
    completion,

    // Evaluation result
    evaluationResult: sdk.evaluationResult,
    resultAvailable: sdk.evaluationResult?.available ?? false,

    // Extra
    groundTruthPatch,

    // Legacy compatibility
    sdkHealth: sdk.sdkReady ? { healthy: true } : null,
    refresh: async () => {
      sdk.reconnect()
    },
    isRefreshing: false,
    isLoading: sdk.isInitializing,

    // Actions
    reconnect: sdk.reconnect,
  }

  return (
    <SDKDataContext.Provider value={contextValue}>
      {children}
    </SDKDataContext.Provider>
  )
}
