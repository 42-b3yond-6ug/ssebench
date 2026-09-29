/**
 * Launch context and its hook; LaunchProvider supplies the value.
 */

import { createContext, useContext } from "react"
import type { LaunchStatus } from "../types/launch"

/** Per-launch entry tracked on the client side */
export interface LaunchEntry {
  status: LaunchStatus
  logs: string[]
}

export interface LaunchContextValue {
  /** All tracked launches keyed by launch_id */
  launches: Map<string, LaunchEntry>
  /** Convenience: array of all launch entries (for iteration in components) */
  allLaunches: LaunchEntry[]
  /** Whether any launch is currently in "launching" state */
  hasActiveLaunches: boolean
  /** Whether connected to the launch WebSocket */
  isConnected: boolean
  /** Get a specific launch entry */
  getLaunch: (launchId: string) => LaunchEntry | undefined
  /** Cancel a specific launch */
  cancel: (launchId: string) => Promise<boolean>
  /** Clear a specific launch entry (removes it) */
  clear: (launchId: string) => Promise<void>
  /** Clear all launch entries */
  clearAll: () => Promise<void>
}

export const LaunchContext = createContext<LaunchContextValue | null>(null)

/**
 * Hook to access multi-launch state from context.
 * Must be used within a LaunchProvider.
 */
export function useLaunchContext(): LaunchContextValue {
  const context = useContext(LaunchContext)
  if (!context) {
    throw new Error("useLaunchContext must be used within a LaunchProvider")
  }
  return context
}
