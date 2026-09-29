/**
 * Settings context and its hook; SettingsProvider supplies the value.
 */

import { createContext, useContext } from "react"
import type { ITheme } from "@xterm/xterm"

export type TerminalThemeName = "gruvbox" | "dracula" | "solarized"

/** Tab bar position for configurable docks */
export type DockTabPosition = "top" | "bottom" | "left" | "right"

export interface Settings {
  terminalTheme: TerminalThemeName
  anthropicApiKey: string | null
  centerTabPosition: DockTabPosition
  bottomTabPosition: DockTabPosition
}

export interface SettingsContextValue extends Settings {
  setTerminalTheme: (theme: TerminalThemeName) => void
  getTerminalTheme: () => ITheme
  setAnthropicApiKey: (key: string | null) => void
  hasAnthropicApiKey: () => boolean
  setCenterTabPosition: (pos: DockTabPosition) => void
  setBottomTabPosition: (pos: DockTabPosition) => void
}

export const SettingsContext = createContext<SettingsContextValue | null>(null)

export function useSettings() {
  const context = useContext(SettingsContext)
  if (!context) {
    throw new Error("useSettings must be used within SettingsProvider")
  }
  return context
}
