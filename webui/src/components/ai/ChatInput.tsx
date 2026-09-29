/**
 * ChatInput Component
 *
 * Auto-growing textarea with send button for chat interface
 */

import { useState, useRef, useEffect, KeyboardEvent } from "react"

interface ChatInputProps {
  onSend: (message: string) => void
  disabled?: boolean
  placeholder?: string
  // Optional: for controlled mode
  value?: string
  onChange?: (value: string) => void
}

export function ChatInput({
  onSend,
  disabled = false,
  placeholder = "Type a message...",
  value: controlledValue,
  onChange: controlledOnChange,
}: ChatInputProps) {
  const [internalMessage, setInternalMessage] = useState("")
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Use controlled value if provided, otherwise use internal state
  const isControlled = controlledValue !== undefined
  const message = isControlled ? controlledValue : internalMessage
  const setMessage = isControlled ? controlledOnChange! : setInternalMessage

  // Auto-grow textarea
  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return

    // Reset height to auto to get proper scrollHeight
    textarea.style.height = "auto"
    // Set height to scrollHeight (content height)
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
  }, [message])

  const handleSend = () => {
    const trimmed = message.trim()
    if (!trimmed || disabled) return

    onSend(trimmed)
    setMessage("")

    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto"
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter to send (without Shift)
    // Shift+Enter for new line
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const canSend = message.trim().length > 0 && !disabled

  return (
    <div className="border-border-subtle bg-bg border-t p-4">
      <div className="mx-auto max-w-3xl">
        {/* ChatGPT-style input container */}
        <div className="relative">
          <textarea
            ref={textareaRef}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={disabled}
            rows={1}
            className="bg-bg-1 border-border text-fg placeholder:text-fg-4 focus:border-gruvbox-aqua focus:ring-gruvbox-aqua w-full resize-none rounded-xl border px-4 py-3 pr-12 text-sm shadow-sm focus:ring-2 focus:outline-none disabled:opacity-50"
            style={{ minHeight: "52px", maxHeight: "200px" }}
          />

          {/* Send button inside textarea */}
          <button
            onClick={handleSend}
            disabled={!canSend}
            className="absolute right-2 bottom-2 flex h-8 w-8 items-center justify-center rounded-lg transition-all disabled:cursor-not-allowed disabled:opacity-40"
            style={{
              backgroundColor: canSend ? "#689d6a" : "#3c3836",
              color: canSend ? "#1d2021" : "#665c54",
            }}
            title={disabled ? "Sending..." : "Send message (Enter)"}
          >
            {disabled ? (
              // Loading spinner
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
            ) : (
              // Send icon
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
                  d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                />
              </svg>
            )}
          </button>
        </div>

        {/* Helper text - subtle */}
        <div className="text-fg-4 mt-2 text-center text-xs">
          {disabled ? (
            <span className="text-gruvbox-yellow flex items-center justify-center gap-1">
              <div className="bg-gruvbox-yellow h-2 w-2 animate-pulse rounded-full" />
              Sending...
            </span>
          ) : (
            <span>Press Enter to send, Shift+Enter for new line</span>
          )}
        </div>
      </div>
    </div>
  )
}
