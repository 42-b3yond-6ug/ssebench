/**
 * Dock Context - Manages active panel state for all docks
 *
 * Tracks which panel is active in each dock (left, center, bottom).
 * Replaces the old ViewContext with a unified panel management system.
 *
 * Scoped per-container (re-created when switching containers).
 */

import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react"

interface DockContextType {
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

const DockContext = createContext<DockContextType | undefined>(undefined)

interface DockProviderProps {
  children: ReactNode
  /** Initial active panels per dock, e.g. { center: "changes", bottom: "logs" } */
  defaultPanels?: Record<string, string>
}

export function DockProvider({ children, defaultPanels = {} }: DockProviderProps) {
  const [activePanels, setActivePanels] = useState<Record<string, string>>(defaultPanels)
  const [dockVisibility, setDockVisibility] = useState<Record<string, boolean>>({})

  const setActivePanel = useCallback((dockId: string, panelId: string) => {
    setActivePanels((prev) => {
      if (prev[dockId] === panelId) return prev
      return { ...prev, [dockId]: panelId }
    })
  }, [])

  const toggleDock = useCallback((dockId: string) => {
    setDockVisibility((prev) => ({
      ...prev,
      [dockId]: !(prev[dockId] ?? true),
    }))
  }, [])

  const isDockVisible = useCallback(
    (dockId: string) => dockVisibility[dockId] ?? true,
    [dockVisibility]
  )

  return (
    <DockContext.Provider
      value={{ activePanels, setActivePanel, dockVisibility, toggleDock, isDockVisible }}
    >
      {children}
    </DockContext.Provider>
  )
}

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
