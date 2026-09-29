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

import { createContext, useContext, ReactNode, useState, useEffect } from "react"
import { useSDKWebSocket } from "../hooks/useSDKWebSocket"
import { fetchGroundTruthPatch } from "../lib/api"
import type {
  ProjectInfo,
  ChangedFile,
  SDKHealthResponse,
  DialogEntry,
  EvaluationResultResponse,
  CompleteEntry,
} from "../types/container"

// =============================================================================
// Context Interface
// =============================================================================

interface SDKDataContextValue {
  // Connection state
  /** Whether SDK is initializing (waiting for connection) */
  isInitializing: boolean
  /** Whether SDK connection is ready */
  sdkReady: boolean
  /** Current retry attempt count during initialization */
  retryAttempt: number
  /** Error message if any */
  error: string | null
  /** SDK version string */
  sdkVersion: string | null

  // Project data
  /** Project metadata from config.yaml */
  project: ProjectInfo | null
  /** List of changed files with stats */
  files: ChangedFile[]
  /** Unified diff string */
  diff: string
  /** Total additions across all files */
  totalAdditions: number
  /** Total deletions across all files */
  totalDeletions: number

  // Agent dialog
  /** All dialog entries from agent conversation */
  dialogEntries: DialogEntry[]
  /** Latest sequence number in dialog */
  latestDialogSeq: number
  /** Whether agent session is complete */
  isComplete: boolean
  /** Completion entry if session is done */
  completion: CompleteEntry | null

  // Evaluation result
  /** Evaluation result (available after agent finishes) */
  evaluationResult: EvaluationResultResponse | null
  /** Whether evaluation result is available */
  resultAvailable: boolean

  // Extra
  /** Ground truth patch (WebUI only, fetched separately) */
  groundTruthPatch: string | null

  // Legacy compatibility (deprecated, use sdkReady instead)
  /** @deprecated Use sdkReady instead */
  sdkHealth: SDKHealthResponse | null
  /** @deprecated WebSocket auto-updates, no manual refresh needed */
  refresh: () => Promise<void>
  /** @deprecated Always false with WebSocket */
  isRefreshing: boolean
  /** @deprecated Use isInitializing instead */
  isLoading: boolean

  // Actions
  /** Manually reconnect the WebSocket */
  reconnect: () => void
}

const SDKDataContext = createContext<SDKDataContextValue | null>(null)

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
      fetchGroundTruthPatch(containerId)
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

// =============================================================================
// Hook
// =============================================================================

/**
 * Hook to access SDK data from context.
 * Must be used within an SDKDataProvider.
 */
export function useSDKDataContext(): SDKDataContextValue {
  const context = useContext(SDKDataContext)
  if (!context) {
    throw new Error("useSDKDataContext must be used within an SDKDataProvider")
  }
  return context
}
