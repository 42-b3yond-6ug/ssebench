/**
 * Server capabilities reported by /api/health
 */

import { createContext, useContext } from "react"

export interface ServerInfo {
  /** False when the server runs with SSEBENCH_WEBUI_TERMINAL=0, or its helper is not built */
  terminal: boolean
  /** Why the terminal is off although it is switched on, and how to fix it */
  terminalHint?: string
}

export const ServerInfoContext = createContext<ServerInfo>({ terminal: true })

export function useServerInfo(): ServerInfo {
  return useContext(ServerInfoContext)
}
