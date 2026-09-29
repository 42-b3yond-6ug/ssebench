/**
 * Contexts that open the global New and Settings panels, provided by App.
 */

import { createContext, useContext } from "react"
import type { NewPanelTab } from "../components/modals/NewPanel"

export interface NewPanelContextValue {
  openNewPanel: (tab: NewPanelTab) => void
}

export const NewPanelContext = createContext<NewPanelContextValue | null>(null)

export function useNewPanel() {
  const context = useContext(NewPanelContext)
  if (!context) {
    throw new Error("useNewPanel must be used within NewPanelProvider")
  }
  return context
}

export interface SettingsPanelContextValue {
  openSettings: () => void
}

export const SettingsPanelContext =
  createContext<SettingsPanelContextValue | null>(null)

export function useSettingsPanel() {
  const context = useContext(SettingsPanelContext)
  if (!context) {
    throw new Error(
      "useSettingsPanel must be used within SettingsPanelProvider"
    )
  }
  return context
}
