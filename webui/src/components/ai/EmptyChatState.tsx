/**
 * EmptyChatState Component
 *
 * Displays when no session is active.
 * Shows welcome message and preset prompt cards to start a conversation.
 * Now includes input box at bottom - clicking presets fills input instead of immediately starting chat.
 */

import { useState } from "react"
import { useSDKDataContext } from "../../context/SDKDataContext"
import {
  getAvailablePresets,
  type DebugPreset,
  type PresetContext,
} from "../../lib/debugPresets"
import { ChatInput } from "./ChatInput"

interface EmptyChatStateProps {
  onSend: (message: string) => void
  disabled?: boolean
}

export function EmptyChatState({ onSend, disabled }: EmptyChatStateProps) {
  const { project, groundTruthPatch } = useSDKDataContext()
  const [inputValue, setInputValue] = useState("")

  const context: PresetContext = {
    projectId: project?.id || "unknown",
    sourceDir: project?.source || "/src",
    language: project?.language || "unknown",
    groundTruthAvailable: !!groundTruthPatch,
    groundTruthContent: groundTruthPatch || undefined,
  }

  const availablePresets = getAvailablePresets(context.groundTruthAvailable)

  // Handle preset click - fill input with preset message
  const handlePresetClick = (preset: DebugPreset) => {
    const message = preset.template(context)
    setInputValue(message)
  }

  // Handle send from input
  const handleSend = (message: string) => {
    onSend(message)
    setInputValue("") // Clear input after sending
  }

  return (
    <div className="flex h-full flex-col">
      {/* Welcome + Presets - Scrollable, centered */}
      <div className="flex-1 overflow-y-auto">
        <div className="flex min-h-full flex-col items-center justify-center p-8">
          {/* Welcome Header */}
          <div className="mb-8 text-center">
            <div className="text-gruvbox-aqua mb-3 text-5xl">✨</div>
            <h2 className="text-fg mb-2 text-2xl font-semibold">
              AI Assistant
            </h2>
            <p className="text-fg-3 text-sm">
              Choose a preset below or type your own question
            </p>
          </div>

          {/* Preset Cards Grid */}
          <div className="grid w-full max-w-3xl grid-cols-1 gap-3 md:grid-cols-2">
            {availablePresets.map((preset) => (
              <PresetCard
                key={preset.id}
                preset={preset}
                onClick={() => handlePresetClick(preset)}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Input - Fixed at bottom */}
      <div className="flex-shrink-0">
        <ChatInput
          value={inputValue}
          onChange={setInputValue}
          onSend={handleSend}
          disabled={disabled}
          placeholder="Ask about this codebase..."
        />
      </div>
    </div>
  )
}

/**
 * Preset card - clickable card for each preset prompt
 */
interface PresetCardProps {
  preset: DebugPreset
  onClick: () => void
}

function PresetCard({ preset, onClick }: PresetCardProps) {
  return (
    <button
      onClick={onClick}
      className="border-border-subtle hover:border-gruvbox-aqua/50 bg-bg-1 hover:bg-bg-2 group relative overflow-hidden rounded-lg border p-4 text-left transition-all"
    >
      <div className="flex items-start gap-3">
        {/* Icon */}
        <span className="text-2xl">{preset.icon}</span>

        {/* Content */}
        <div className="flex-1">
          <div className="text-fg mb-1 text-sm font-medium">{preset.label}</div>
          <div className="text-fg-3 text-xs leading-relaxed">
            {preset.description}
          </div>
        </div>

        {/* Arrow indicator on hover */}
        <svg
          className="text-gruvbox-aqua h-5 w-5 flex-shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M13 7l5 5m0 0l-5 5m5-5H6"
          />
        </svg>
      </div>

      {/* Ground truth badge */}
      {preset.requiresGroundTruth && (
        <div className="text-fg-4 mt-2 flex items-center gap-1 text-xs">
          <span>📊</span>
          <span>Requires ground truth</span>
        </div>
      )}
    </button>
  )
}
