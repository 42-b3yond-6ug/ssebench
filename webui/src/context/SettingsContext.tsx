/**
 * Settings Context - Global application settings
 *
 * Manages user preferences like terminal themes, font sizes, etc.
 * Settings are persisted to localStorage.
 */

import { useState, useEffect, ReactNode } from "react"
import type { ITheme } from "@xterm/xterm"
import {
  SettingsContext,
  type Settings,
  type TerminalThemeName,
  type DockTabPosition,
} from "./useSettings"

// Terminal theme definitions
const terminalThemes: Record<TerminalThemeName, ITheme> = {
  gruvbox: {
    background: "#0d0f10",
    foreground: "#ebdbb2",
    cursor: "#ebdbb2",
    cursorAccent: "#0d0f10",
    selectionBackground: "#504945",
    selectionForeground: "#ebdbb2",
    black: "#282828",
    red: "#cc241d",
    green: "#98971a",
    yellow: "#d79921",
    blue: "#458588",
    magenta: "#b16286",
    cyan: "#689d6a",
    white: "#a89984",
    brightBlack: "#928374",
    brightRed: "#fb4934",
    brightGreen: "#b8bb26",
    brightYellow: "#fabd2f",
    brightBlue: "#83a598",
    brightMagenta: "#d3869b",
    brightCyan: "#8ec07c",
    brightWhite: "#ebdbb2",
  },
  dracula: {
    background: "#282a36",
    foreground: "#f8f8f2",
    cursor: "#f8f8f2",
    cursorAccent: "#282a36",
    selectionBackground: "#44475a",
    selectionForeground: "#f8f8f2",
    black: "#21222c",
    red: "#ff5555",
    green: "#50fa7b",
    yellow: "#f1fa8c",
    blue: "#bd93f9",
    magenta: "#ff79c6",
    cyan: "#8be9fd",
    white: "#f8f8f2",
    brightBlack: "#6272a4",
    brightRed: "#ff6e6e",
    brightGreen: "#69ff94",
    brightYellow: "#ffffa5",
    brightBlue: "#d6acff",
    brightMagenta: "#ff92df",
    brightCyan: "#a4ffff",
    brightWhite: "#ffffff",
  },
  solarized: {
    background: "#002b36",
    foreground: "#839496",
    cursor: "#839496",
    cursorAccent: "#002b36",
    selectionBackground: "#073642",
    selectionForeground: "#93a1a1",
    black: "#073642",
    red: "#dc322f",
    green: "#859900",
    yellow: "#b58900",
    blue: "#268bd2",
    magenta: "#d33682",
    cyan: "#2aa198",
    white: "#eee8d5",
    brightBlack: "#002b36",
    brightRed: "#cb4b16",
    brightGreen: "#586e75",
    brightYellow: "#657b83",
    brightBlue: "#839496",
    brightMagenta: "#6c71c4",
    brightCyan: "#93a1a1",
    brightWhite: "#fdf6e3",
  },
}

const STORAGE_KEY = "ssebench-settings"

const defaultSettings: Settings = {
  terminalTheme: "gruvbox",
  anthropicApiKey: null,
  centerTabPosition: "top",
  bottomTabPosition: "right",
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(() => {
    // Load from localStorage
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        return { ...defaultSettings, ...JSON.parse(stored) }
      }
    } catch (error) {
      console.error("[Settings] Failed to load from localStorage:", error)
    }
    return defaultSettings
  })

  // Save to localStorage when settings change
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
    } catch (error) {
      console.error("[Settings] Failed to save to localStorage:", error)
    }
  }, [settings])

  const setTerminalTheme = (theme: TerminalThemeName) => {
    setSettings((prev) => ({ ...prev, terminalTheme: theme }))
  }

  const getTerminalTheme = () => {
    return terminalThemes[settings.terminalTheme]
  }

  const setAnthropicApiKey = (key: string | null) => {
    setSettings((prev) => ({ ...prev, anthropicApiKey: key }))
  }

  const hasAnthropicApiKey = () => {
    return (
      settings.anthropicApiKey !== null &&
      settings.anthropicApiKey.trim() !== ""
    )
  }

  const setCenterTabPosition = (pos: DockTabPosition) => {
    setSettings((prev) => ({ ...prev, centerTabPosition: pos }))
  }

  const setBottomTabPosition = (pos: DockTabPosition) => {
    setSettings((prev) => ({ ...prev, bottomTabPosition: pos }))
  }

  return (
    <SettingsContext.Provider
      value={{
        ...settings,
        setTerminalTheme,
        getTerminalTheme,
        setAnthropicApiKey,
        hasAnthropicApiKey,
        setCenterTabPosition,
        setBottomTabPosition,
      }}
    >
      {children}
    </SettingsContext.Provider>
  )
}
