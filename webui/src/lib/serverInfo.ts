/**
 * Server capabilities reported by /api/health
 */

import { createContext, useContext } from "react"

export interface ServerInfo {
  /** False when the server runs with SSEBENCH_WEBUI_TERMINAL=0 */
  terminal: boolean
}

export const ServerInfoContext = createContext<ServerInfo>({ terminal: true })

export function useServerInfo(): ServerInfo {
  return useContext(ServerInfoContext)
}
