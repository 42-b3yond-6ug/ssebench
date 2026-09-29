/**
 * Dock Context - Manages active panel state for all docks
 *
 * Tracks which panel is active in each dock (left, center, bottom).
 * Replaces the old ViewContext with a unified panel management system.
 *
 * Scoped per-container (re-created when switching containers).
 */

import { useCallback, useState, type ReactNode } from "react"
import { DockContext } from "./useDock"

interface DockProviderProps {
  children: ReactNode
  /** Initial active panels per dock, e.g. { center: "changes", bottom: "logs" } */
  defaultPanels?: Record<string, string>
}

export function DockProvider({
  children,
  defaultPanels = {},
}: DockProviderProps) {
  const [activePanels, setActivePanels] =
    useState<Record<string, string>>(defaultPanels)
  const [dockVisibility, setDockVisibility] = useState<Record<string, boolean>>(
    {}
  )

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
      value={{
        activePanels,
        setActivePanel,
        dockVisibility,
        toggleDock,
        isDockVisible,
      }}
    >
      {children}
    </DockContext.Provider>
  )
}
