/**
 * SDK data context and its hook; SDKDataProvider supplies the value.
 */

import { createContext, useContext } from "react"
import type {
  ProjectInfo,
  ChangedFile,
  SDKHealthResponse,
  DialogEntry,
  EvaluationResultResponse,
  CompleteEntry,
} from "../types/container"

export interface SDKDataContextValue {
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

export const SDKDataContext = createContext<SDKDataContextValue | null>(null)

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
