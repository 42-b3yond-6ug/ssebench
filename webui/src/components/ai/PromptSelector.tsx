/**
 * Prompt Selector Component for Debug View
 *
 * Allows users to select a preset prompt or enter a custom message
 * before launching OpenCode.
 */

import { useState, useEffect, useMemo } from "react"
import {
  debugPresets,
  getAvailablePresets,
  type DebugPreset,
  type PresetContext,
} from "../../lib/debugPresets"
import { OpenCodeClient } from "../../lib/opencodeClient"

interface PromptSelectorProps {
  /** Callback when user confirms prompt */
  onSubmit: (message: string) => void
  /** Callback when user cancels */
  onCancel: () => void
  /** Context for generating preset messages */
  context: PresetContext
  /** Container ID for health check */
  containerId: string
}

export function PromptSelector({
  onSubmit,
  onCancel,
  context,
  containerId,
}: PromptSelectorProps) {
  const [customPrompt, setCustomPrompt] = useState("")
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null)
  const [isHealthy, setIsHealthy] = useState(false)
  const [isConnecting, setIsConnecting] = useState(false)
  const [isCheckingHealth, setIsCheckingHealth] = useState(true)

  const client = useMemo(() => new OpenCodeClient(containerId), [containerId])
  const availablePresets = getAvailablePresets(context.groundTruthAvailable)

  // Check OpenCode health status
  useEffect(() => {
    let mounted = true
    let pollInterval: NodeJS.Timeout | null = null

    const checkHealth = async () => {
      try {
        const health = await client.checkHealth()
        if (mounted) {
          setIsHealthy(health.healthy)
          setIsCheckingHealth(false)

          // If process is running but not healthy, we're connecting
          if (health.processRunning && !health.healthy) {
            setIsConnecting(true)
            // Keep polling while connecting
            if (!pollInterval) {
              pollInterval = setInterval(() => {
                checkHealth()
              }, 2000)
            }
          } else {
            setIsConnecting(false)
            // Stop polling once connected
            if (pollInterval) {
              clearInterval(pollInterval)
              pollInterval = null
            }
          }
        }
      } catch {
        if (mounted) {
          setIsHealthy(false)
          setIsConnecting(false)
          setIsCheckingHealth(false)
        }
      }
    }

    checkHealth()

    return () => {
      mounted = false
      if (pollInterval) {
        clearInterval(pollInterval)
      }
    }
  }, [client])

  // Get the preset object if one is selected
  const activePreset = selectedPreset
    ? debugPresets.find((p) => p.id === selectedPreset)
    : null

  // Get the final message to send
  const getFinalMessage = (): string => {
    if (customPrompt.trim()) {
      return customPrompt.trim()
    }
    if (activePreset) {
      return activePreset.template(context)
    }
    return ""
  }

  const handleSubmit = () => {
    const message = getFinalMessage()
    if (message) {
      onSubmit(message)
    }
  }

  const handlePresetClick = (presetId: string) => {
    setSelectedPreset(presetId)
    setCustomPrompt("") // Clear custom prompt when preset is selected
  }

  const handleCustomPromptChange = (value: string) => {
    setCustomPrompt(value)
    if (value.trim()) {
      setSelectedPreset(null) // Clear preset when typing custom prompt
    }
  }

  const hasPrompt = customPrompt.trim() !== "" || selectedPreset !== null
  const canSubmit = hasPrompt && isHealthy

  return (
    <div className="flex h-full w-full items-center justify-center p-8">
      <div className="bg-bg-1 border-border-subtle w-full max-w-3xl rounded-lg border shadow-lg">
        {/* Header */}
        <div className="border-border-subtle border-b px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="text-gruvbox-aqua text-2xl">🤖</div>
            <div>
              <h2 className="text-fg-1 text-lg font-semibold">
                OpenCode Debug Assistant
              </h2>
              <p className="text-fg-3 text-sm">
                Choose a preset or write a custom prompt to get started
              </p>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="space-y-6 p-6">
          {/* Custom Prompt */}
          <div>
            <label
              htmlFor="custom-prompt"
              className="text-fg-2 mb-2 block text-sm font-medium"
            >
              Custom Prompt
            </label>
            <textarea
              id="custom-prompt"
              value={customPrompt}
              onChange={(e) => handleCustomPromptChange(e.target.value)}
              placeholder="Enter your message for OpenCode..."
              className="bg-bg-2 border-border-subtle text-fg-1 placeholder:text-fg-4 focus:border-gruvbox-aqua focus:ring-gruvbox-aqua h-32 w-full rounded-md border px-3 py-2 text-sm focus:ring-1 focus:outline-none"
              autoFocus
            />
          </div>

          {/* Divider */}
          <div className="flex items-center gap-3">
            <div className="bg-border-subtle h-px flex-1" />
            <span className="text-fg-4 text-xs font-medium">
              OR CHOOSE A PRESET
            </span>
            <div className="bg-border-subtle h-px flex-1" />
          </div>

          {/* Preset Buttons */}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {availablePresets.map((preset) => (
              <PresetButton
                key={preset.id}
                preset={preset}
                isSelected={selectedPreset === preset.id}
                onClick={() => handlePresetClick(preset.id)}
              />
            ))}
          </div>

          {/* Preview selected preset */}
          {activePreset && !customPrompt.trim() && (
            <div className="bg-bg-2 border-border-subtle rounded-md border p-4">
              <div className="text-fg-3 mb-2 flex items-center gap-2 text-xs font-medium">
                <span>📋</span>
                <span>PREVIEW</span>
              </div>
              <div className="text-fg-2 max-h-48 overflow-y-auto text-sm whitespace-pre-wrap">
                {activePreset.template(context)}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="border-border-subtle border-t px-6 py-4">
          {/* Connection Status Bar */}
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              {isCheckingHealth ? (
                <>
                  <div className="border-gruvbox-blue h-4 w-4 animate-spin rounded-full border-2 border-t-transparent" />
                  <span className="text-fg-3 text-xs">
                    Checking OpenCode server...
                  </span>
                </>
              ) : isConnecting ? (
                <>
                  <div className="border-gruvbox-blue h-4 w-4 animate-spin rounded-full border-2 border-t-transparent" />
                  <span className="text-gruvbox-blue text-xs font-medium">
                    Starting OpenCode server...
                  </span>
                </>
              ) : isHealthy ? (
                <>
                  <div className="bg-gruvbox-green h-3 w-3 rounded-full" />
                  <span className="text-gruvbox-green text-xs font-medium">
                    OpenCode connected
                  </span>
                </>
              ) : (
                <>
                  <div className="bg-gruvbox-red h-3 w-3 rounded-full" />
                  <span className="text-gruvbox-red text-xs font-medium">
                    OpenCode unavailable
                  </span>
                </>
              )}
            </div>
            <div className="text-fg-4 text-xs">
              {context.groundTruthAvailable ? (
                <span className="text-gruvbox-green">
                  ✓ Ground truth available
                </span>
              ) : (
                <span className="text-gruvbox-yellow">⚠ No ground truth</span>
              )}
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-3">
            <button
              onClick={onCancel}
              className="text-fg-3 hover:bg-bg-2 rounded-md px-4 py-2 text-sm font-medium transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={!canSubmit}
              title={
                !isHealthy
                  ? "Waiting for OpenCode server..."
                  : !hasPrompt
                    ? "Select a preset or enter a custom prompt"
                    : "Start conversation with OpenCode"
              }
              className="bg-gruvbox-aqua hover:bg-gruvbox-aqua/90 disabled:bg-bg-3 disabled:text-fg-4 rounded-md px-4 py-2 text-sm font-medium text-black transition-colors disabled:cursor-not-allowed"
            >
              Start Conversation
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

interface PresetButtonProps {
  preset: DebugPreset
  isSelected: boolean
  onClick: () => void
}

function PresetButton({ preset, isSelected, onClick }: PresetButtonProps) {
  return (
    <button
      onClick={onClick}
      className={`group relative overflow-hidden rounded-lg border p-4 text-left transition-all ${
        isSelected
          ? "border-gruvbox-aqua bg-gruvbox-aqua/10"
          : "border-border-subtle bg-bg-2 hover:border-gruvbox-aqua/50 hover:bg-bg-3"
      } `}
    >
      <div className="flex items-start gap-3">
        <span className="text-2xl">{preset.icon}</span>
        <div className="flex-1">
          <div
            className={`mb-1 text-sm font-medium ${
              isSelected ? "text-gruvbox-aqua" : "text-fg-1"
            }`}
          >
            {preset.label}
          </div>
          <div className="text-fg-3 text-xs">{preset.description}</div>
        </div>
        {isSelected && (
          <div className="text-gruvbox-aqua">
            <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                clipRule="evenodd"
              />
            </svg>
          </div>
        )}
      </div>
      {preset.requiresGroundTruth && (
        <div className="text-fg-4 mt-2 flex items-center gap-1 text-xs">
          <span>📊</span>
          <span>Requires ground truth</span>
        </div>
      )}
    </button>
  )
}
