/**
 * Settings Panel - Modal for application settings
 *
 * Allows users to configure preferences like terminal themes and API keys.
 */

import { useEffect, useState } from "react"
import {
  useSettings,
  type TerminalThemeName,
  type DockTabPosition,
} from "../../context/useSettings"

interface SettingsPanelProps {
  isOpen: boolean
  onClose: () => void
}

export function SettingsPanel({ isOpen, onClose }: SettingsPanelProps) {
  const {
    terminalTheme,
    setTerminalTheme,
    anthropicApiKey,
    setAnthropicApiKey,
    centerTabPosition,
    setCenterTabPosition,
    bottomTabPosition,
    setBottomTabPosition,
  } = useSettings()
  const [apiKeyInput, setApiKeyInput] = useState(anthropicApiKey || "")
  const [showApiKey, setShowApiKey] = useState(false)

  // Sync input with saved API key each time the panel opens
  const [wasOpen, setWasOpen] = useState(isOpen)
  if (isOpen !== wasOpen) {
    setWasOpen(isOpen)
    if (isOpen) setApiKeyInput(anthropicApiKey || "")
  }

  // Handle Escape key
  useEffect(() => {
    if (!isOpen) return

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose()
      }
    }

    document.addEventListener("keydown", handleEscape)
    return () => document.removeEventListener("keydown", handleEscape)
  }, [isOpen, onClose])

  if (!isOpen) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          className="bg-bg border-border relative w-full max-w-2xl rounded-lg border shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <header className="border-border flex items-center justify-between border-b px-6 py-4">
            <div>
              <h2 className="text-fg text-lg font-semibold">Settings</h2>
              <p className="text-fg-4 text-sm">Configure your preferences</p>
            </div>
            <button
              onClick={onClose}
              className="text-fg-4 hover:text-fg hover:bg-bg-1 rounded p-2 transition-colors"
              title="Close (Esc)"
            >
              <svg
                className="h-5 w-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </header>

          {/* Content */}
          <div className="max-h-[600px] overflow-y-auto p-6">
            {/* API Configuration Section */}
            <section className="mb-8">
              <h3 className="text-fg mb-3 text-base font-medium">
                API Configuration
              </h3>
              <p className="text-fg-4 mb-4 text-sm">
                Configure your Anthropic API key for OpenCode
              </p>

              <div className="bg-bg-1 border-border rounded-lg border p-4">
                <label
                  htmlFor="api-key"
                  className="text-fg-3 mb-2 block text-sm font-medium"
                >
                  Anthropic API Key
                </label>
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <input
                      id="api-key"
                      type={showApiKey ? "text" : "password"}
                      value={apiKeyInput}
                      onChange={(e) => setApiKeyInput(e.target.value)}
                      placeholder="sk-ant-..."
                      className="bg-bg-2 border-border text-fg placeholder:text-fg-4 focus:border-gruvbox-aqua focus:ring-gruvbox-aqua w-full rounded border px-3 py-2 font-mono text-sm focus:ring-1 focus:outline-none"
                    />
                    <button
                      onClick={() => setShowApiKey(!showApiKey)}
                      className="text-fg-4 hover:text-fg absolute top-1/2 right-2 -translate-y-1/2 p-1"
                      title={showApiKey ? "Hide" : "Show"}
                    >
                      {showApiKey ? (
                        <svg
                          className="h-4 w-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"
                          />
                        </svg>
                      ) : (
                        <svg
                          className="h-4 w-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                          />
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                          />
                        </svg>
                      )}
                    </button>
                  </div>
                  <button
                    onClick={() => {
                      const key = apiKeyInput.trim()
                      setAnthropicApiKey(key || null)
                      setApiKeyInput(key)
                    }}
                    className="bg-gruvbox-aqua hover:bg-gruvbox-aqua/80 text-bg rounded px-4 py-2 text-sm font-medium transition-colors"
                  >
                    Save
                  </button>
                </div>
                <p className="text-fg-4 mt-2 text-xs">
                  The key is saved in this browser&apos;s localStorage. When you
                  start an AI session, the web UI server passes it to OpenCode
                  inside the run container, which keeps it there; remove the
                  container when you are done.
                  <br />
                  Get your key from{" "}
                  <a
                    href="https://console.anthropic.com/settings/keys"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-gruvbox-aqua hover:underline"
                  >
                    Anthropic Console
                  </a>
                </p>
              </div>
            </section>

            {/* Terminal Theme Section */}
            <section className="mb-8">
              <h3 className="text-fg mb-3 text-base font-medium">
                Terminal Theme
              </h3>
              <p className="text-fg-4 mb-4 text-sm">
                Choose a color scheme for the terminal
              </p>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <ThemeOption
                  name="Gruvbox"
                  value="gruvbox"
                  description="Retro groove dark theme"
                  colors={[
                    "#282828",
                    "#cc241d",
                    "#98971a",
                    "#d79921",
                    "#458588",
                    "#b16286",
                    "#689d6a",
                    "#ebdbb2",
                  ]}
                  isSelected={terminalTheme === "gruvbox"}
                  onSelect={() => setTerminalTheme("gruvbox")}
                />
                <ThemeOption
                  name="Dracula"
                  value="dracula"
                  description="Dark theme with vibrant colors"
                  colors={[
                    "#282a36",
                    "#ff5555",
                    "#50fa7b",
                    "#f1fa8c",
                    "#bd93f9",
                    "#ff79c6",
                    "#8be9fd",
                    "#f8f8f2",
                  ]}
                  isSelected={terminalTheme === "dracula"}
                  onSelect={() => setTerminalTheme("dracula")}
                />
                <ThemeOption
                  name="Solarized"
                  value="solarized"
                  description="Precision colors for readability"
                  colors={[
                    "#002b36",
                    "#dc322f",
                    "#859900",
                    "#b58900",
                    "#268bd2",
                    "#d33682",
                    "#2aa198",
                    "#839496",
                  ]}
                  isSelected={terminalTheme === "solarized"}
                  onSelect={() => setTerminalTheme("solarized")}
                />
              </div>
            </section>

            {/* Layout Section */}
            <section className="mb-8">
              <h3 className="text-fg mb-3 text-base font-medium">Layout</h3>
              <p className="text-fg-4 mb-4 text-sm">
                Configure tab bar positions for dock panels
              </p>

              <div className="space-y-4">
                {/* Center dock tab position */}
                <div className="bg-bg-1 border-border rounded-lg border p-4">
                  <label className="text-fg-3 mb-2 block text-sm font-medium">
                    Center Dock Tabs
                  </label>
                  <p className="text-fg-4 mb-3 text-xs">
                    Position of the tab bar for Changes, Files, AI, Terminal,
                    and Evaluation panels
                  </p>
                  <TabPositionPicker
                    value={centerTabPosition}
                    onChange={setCenterTabPosition}
                  />
                </div>

                {/* Bottom dock tab position */}
                <div className="bg-bg-1 border-border rounded-lg border p-4">
                  <label className="text-fg-3 mb-2 block text-sm font-medium">
                    Bottom Dock Tabs
                  </label>
                  <p className="text-fg-4 mb-3 text-xs">
                    Position of the tab bar for Terminal and Logs panels
                  </p>
                  <TabPositionPicker
                    value={bottomTabPosition}
                    onChange={setBottomTabPosition}
                  />
                </div>
              </div>
            </section>
          </div>

          {/* Footer */}
          <footer className="border-border flex items-center justify-end gap-3 border-t px-6 py-4">
            <button
              onClick={onClose}
              className="hover:bg-bg-1 text-fg rounded px-4 py-2 text-sm transition-colors"
            >
              Close
            </button>
          </footer>
        </div>
      </div>
    </>
  )
}

interface ThemeOptionProps {
  name: string
  value: TerminalThemeName
  description: string
  colors: string[]
  isSelected: boolean
  onSelect: () => void
}

function ThemeOption({
  name,
  description,
  colors,
  isSelected,
  onSelect,
}: ThemeOptionProps) {
  return (
    <button
      onClick={onSelect}
      className={`border-border hover:border-gruvbox-orange/50 group relative flex flex-col gap-3 rounded-lg border-2 p-4 text-left transition-all ${
        isSelected
          ? "border-gruvbox-orange bg-gruvbox-orange/5"
          : "bg-bg-1 hover:bg-bg-2"
      }`}
    >
      {/* Selected indicator */}
      {isSelected && (
        <div className="absolute top-2 right-2">
          <svg
            className="text-gruvbox-orange h-5 w-5"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
              clipRule="evenodd"
            />
          </svg>
        </div>
      )}

      {/* Theme name */}
      <div>
        <h4
          className={`text-sm font-medium ${isSelected ? "text-gruvbox-orange" : "text-fg"}`}
        >
          {name}
        </h4>
        <p className="text-fg-4 text-xs">{description}</p>
      </div>

      {/* Color palette preview */}
      <div className="flex gap-1">
        {colors.map((color, i) => (
          <div
            key={i}
            className="h-6 flex-1 rounded-sm"
            style={{ backgroundColor: color }}
            title={color}
          />
        ))}
      </div>
    </button>
  )
}

/** Visual tab position picker — shows a mini layout diagram */
function TabPositionPicker({
  value,
  onChange,
}: {
  value: DockTabPosition
  onChange: (pos: DockTabPosition) => void
}) {
  const positions: { pos: DockTabPosition; label: string }[] = [
    { pos: "top", label: "Top" },
    { pos: "bottom", label: "Bottom" },
    { pos: "left", label: "Left" },
    { pos: "right", label: "Right" },
  ]

  return (
    <div className="flex gap-2">
      {positions.map(({ pos, label }) => {
        const isActive = value === pos
        return (
          <button
            key={pos}
            onClick={() => onChange(pos)}
            className={`rounded px-4 py-2 text-sm font-medium transition-colors ${
              isActive
                ? "bg-gruvbox-aqua text-bg"
                : "bg-bg-2 text-fg-4 hover:text-fg hover:bg-bg-3"
            }`}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}
