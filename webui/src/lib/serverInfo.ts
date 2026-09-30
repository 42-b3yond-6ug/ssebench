/**
 * Server capabilities reported by /api/health
 */

import { createContext, useContext } from "react"

export interface ServerInfo {
  /**
   * False when the server runs with SSEBENCH_WEBUI_TERMINAL=0, or hosted, or
   * its helper is not built, or its runner backend cannot run commands in a run
   */
  terminal: boolean
  /** Why the terminal is off although it is switched on, and how to fix it */
  terminalHint?: string
  /** False when the AI assistant, which runs commands in the run's container, is off: hosted, or no exec */
  assistant: boolean
  /** Hosted (showcase) mode: the server only shows runs and changes nothing */
  readOnly: boolean
}

export const DEFAULT_SERVER_INFO: ServerInfo = {
  terminal: true,
  assistant: true,
  readOnly: false,
}

export const ServerInfoContext = createContext<ServerInfo>(DEFAULT_SERVER_INFO)

export function useServerInfo(): ServerInfo {
  return useContext(ServerInfoContext)
}
