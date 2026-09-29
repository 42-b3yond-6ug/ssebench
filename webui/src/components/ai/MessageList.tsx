/**
 * MessageList Component
 *
 * Displays a list of dialog entries (messages, thinking, tools)
 * Reuses rendering components from AgentPanel for consistency
 */

import { useEffect, useRef, useState } from "react"
import type { DialogEntry } from "../../types/container"
import type { ReasoningContent } from "../../types/opencode"

// Import rendering components from AgentPanel
// We'll need to create a shared module for these
import {
  PromptMessage,
  AssistantMessage,
  ThinkingMessage,
  ToolMessage,
} from "./MessageComponents"
import { ReasoningList } from "./ReasoningBlock"

interface MessageListProps {
  entries: DialogEntry[]
  isLoading?: boolean
  isStreaming?: boolean
  streamingMessageId?: string | null
  reasoningContent?: Map<string, ReasoningContent>
}

export function MessageList({
  entries,
  isLoading = false,
  isStreaming = false,
  streamingMessageId = null,
  reasoningContent = new Map(),
}: MessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const lastContentRef = useRef<string>("")

  // Convert reasoning map to array
  const reasonings = Array.from(reasoningContent.values())

  // Auto-scroll to bottom when new entries arrive or content changes during streaming
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      // Calculate content signature to detect changes
      const contentSignature = JSON.stringify(entries) + reasonings.length

      // Scroll if content changed or streaming is active
      if (contentSignature !== lastContentRef.current || isStreaming) {
        scrollRef.current.scrollTop = scrollRef.current.scrollHeight
        lastContentRef.current = contentSignature
      }
    }
  }, [entries, autoScroll, isStreaming, reasonings.length])

  // Detect if user has scrolled up (disable auto-scroll)
  const handleScroll = () => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50
    setAutoScroll(isAtBottom)
  }

  if (entries.length === 0 && !isLoading) {
    return <EmptyState />
  }

  return (
    <div ref={scrollRef} onScroll={handleScroll} className="min-w-0 p-4">
      <div className="flex flex-col gap-4">
        {entries.map((entry) => (
          <DialogEntryComponent key={entry.seq} entry={entry} />
        ))}

        {/* Reasoning content - shown above streaming indicator */}
        {reasonings.length > 0 && <ReasoningList reasonings={reasonings} />}

        {/* Streaming indicator - shows when AI is actively generating */}
        {isStreaming && streamingMessageId && (
          <div className="border-gruvbox-aqua/20 bg-gruvbox-aqua/5 rounded-lg border p-3">
            <div className="text-fg-3 flex items-center gap-3 text-sm">
              <div className="flex gap-1">
                <div className="bg-gruvbox-aqua h-2 w-2 animate-bounce rounded-full" />
                <div
                  className="bg-gruvbox-aqua h-2 w-2 animate-bounce rounded-full"
                  style={{ animationDelay: "0.1s" }}
                />
                <div
                  className="bg-gruvbox-aqua h-2 w-2 animate-bounce rounded-full"
                  style={{ animationDelay: "0.2s" }}
                />
              </div>
              <div className="text-xs">Generating response...</div>
            </div>
          </div>
        )}

        {/* Loading indicator - shows when waiting for session/connection */}
        {isLoading && !isStreaming && (
          <div className="border-gruvbox-aqua/20 bg-gruvbox-aqua/5 rounded-lg border p-4">
            <div className="text-fg-3 flex items-center gap-3 text-sm">
              <div className="border-gruvbox-aqua relative h-5 w-5">
                <div className="border-gruvbox-aqua absolute h-5 w-5 animate-spin rounded-full border-2 border-t-transparent" />
                <div className="border-gruvbox-aqua absolute h-5 w-5 animate-ping rounded-full border opacity-20" />
              </div>
              <div>
                <div className="font-medium">AI is thinking...</div>
                <div className="text-fg-4 text-xs">
                  This may take a moment depending on the complexity of your
                  request
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Scroll to bottom button (when not auto-scrolling) */}
      {!autoScroll && (
        <button
          onClick={() => {
            if (scrollRef.current) {
              scrollRef.current.scrollTop = scrollRef.current.scrollHeight
              setAutoScroll(true)
            }
          }}
          className="bg-gruvbox-aqua hover:bg-gruvbox-aqua/80 text-bg fixed right-8 bottom-24 rounded-full p-2 shadow-lg transition-all"
          title="Scroll to bottom"
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
              d="M19 14l-7 7m0 0l-7-7m7 7V3"
            />
          </svg>
        </button>
      )}
    </div>
  )
}

/**
 * Route each dialog entry to its appropriate component
 */
function DialogEntryComponent({ entry }: { entry: DialogEntry }) {
  switch (entry.type) {
    case "prompt":
      return <PromptMessage entry={entry} />
    case "message":
      return <AssistantMessage entry={entry} />
    case "thinking":
      return <ThinkingMessage entry={entry} />
    case "tool":
      return <ToolMessage entry={entry} />
    default:
      return null
  }
}

/**
 * Empty state when no messages yet
 */
function EmptyState() {
  return (
    <div className="text-fg-4 flex h-full flex-col items-center justify-center px-4">
      <svg
        className="mb-4 h-16 w-16 opacity-20"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
        />
      </svg>
      <h3 className="text-fg-3 mb-2 text-sm font-medium">
        Start a conversation
      </h3>
      <p className="max-w-xs text-center text-xs">
        Ask OpenCode anything about this codebase. It can help you debug,
        analyze changes, or suggest improvements.
      </p>
    </div>
  )
}
