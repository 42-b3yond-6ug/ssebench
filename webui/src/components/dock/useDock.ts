/**
 * Dock context and its hooks; DockProvider supplies the value.
 */

import { createContext, useContext } from "react"

export interface DockContextType {
  /** Map of dockId -> active panelId */
  activePanels: Record<string, string>
  /** Set the active panel for a given dock */
  setActivePanel: (dockId: string, panelId: string) => void
  /** Map of dockId -> visibility */
  dockVisibility: Record<string, boolean>
  /** Toggle a dock's visibility */
  toggleDock: (dockId: string) => void
  /** Check if a dock is visible (defaults to true) */
  isDockVisible: (dockId: string) => boolean
}

export const DockContext = createContext<DockContextType | undefined>(undefined)

export function useDock() {
  const context = useContext(DockContext)
  if (!context) {
    throw new Error("useDock must be used within a DockProvider")
  }
  return context
}

/**
 * Convenience hook: get the active panel ID for a specific dock.
 * Returns undefined if no panel is set for this dock.
 */
export function useActivePanelId(dockId: string): string | undefined {
  const { activePanels } = useDock()
  return activePanels[dockId]
}
