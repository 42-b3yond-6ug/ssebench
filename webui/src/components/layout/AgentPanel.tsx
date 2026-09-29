/**
 * Agent Dialog Panel - Conversational timeline
 *
 * Shows the agent's interaction history including:
 * - Session initialization
 * - User prompts
 * - Agent responses
 * - Thinking/reasoning blocks
 * - Tool calls with status
 * - Session completion
 */

import { useState, useEffect, useRef, useMemo, useCallback } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { useSDKDataContext } from "../../context/SDKDataContext"
import type {
  DialogEntry,
  InitEntry,
  PromptEntry,
  MessageEntry,
  ThinkingEntry,
  ToolEntry,
  CompleteEntry,
} from "../../types/container"

// =============================================================================
// Entry Components
// =============================================================================

/** Session initialization entry */
function InitMessage({ entry }: { entry: InitEntry }) {
  return (
    <div className="bg-bg-1 border-border-subtle rounded-lg border p-3">
      <div className="text-fg-4 mb-2 flex items-center gap-2 text-xs">
        <svg
          className="text-gruvbox-blue h-4 w-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M13 10V3L4 14h7v7l9-11h-7z"
          />
        </svg>
        <span>Session Started</span>
        <span className="text-fg-4/60">{formatTime(entry.ts)}</span>
      </div>
      <div className="text-fg-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <div>
          <span className="text-fg-4">Agent:</span>{" "}
          <span className="text-gruvbox-aqua">{entry.data.agent}</span>
        </div>
        <div>
          <span className="text-fg-4">Model:</span>{" "}
          <span className="text-gruvbox-purple">{entry.data.model}</span>
        </div>
        <div className="col-span-2 truncate">
          <span className="text-fg-4">Task:</span>{" "}
          <span className="font-mono">{entry.data.task}</span>
        </div>
      </div>
    </div>
  )
}

/** User prompt entry */
function PromptMessage({ entry }: { entry: PromptEntry }) {
  const [isExpanded, setIsExpanded] = useState(false)
  const isLong = entry.content.length > 300

  return (
    <div className="bg-bg-2 rounded-lg p-3">
      <div className="text-fg-4 mb-2 flex items-center gap-2 text-xs">
        <svg
          className="text-gruvbox-green h-4 w-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
          />
        </svg>
        <span>Task Prompt</span>
        <span className="text-fg-4/60">{formatTime(entry.ts)}</span>
      </div>
      <div className="text-fg text-sm leading-relaxed whitespace-pre-wrap">
        {isLong && !isExpanded
          ? entry.content.slice(0, 300) + "..."
          : entry.content}
      </div>
      {isLong && (
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="text-gruvbox-aqua mt-2 text-xs hover:underline"
        >
          {isExpanded ? "Show less" : "Show more"}
        </button>
      )}
    </div>
  )
}

/** Assistant message entry */
function AssistantMessage({ entry }: { entry: MessageEntry }) {
  return (
    <div className="border-gruvbox-aqua border-l-2 pl-3">
      <div className="text-fg-4 mb-2 flex items-center gap-2 text-xs">
        <svg
          className="text-gruvbox-aqua h-4 w-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
          />
        </svg>
        <span>Assistant</span>
        <span className="text-fg-4/60">{formatTime(entry.ts)}</span>
        {entry.tokens && (
          <span className="text-fg-4/40 ml-auto text-[10px]">
            {entry.tokens.in}↓ {entry.tokens.out}↑
          </span>
        )}
      </div>
      <div className="text-fg prose-invert prose-sm max-w-none text-sm leading-relaxed">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            // Style code blocks
            code: ({ className, children, ...props }) => {
              const isInline = !className
              if (isInline) {
                return (
                  <code
                    className="bg-bg-1 text-gruvbox-yellow rounded px-1.5 py-0.5 font-mono text-xs"
                    {...props}
                  >
                    {children}
                  </code>
                )
              }
              return (
                <code
                  className="bg-bg-1 block overflow-x-auto rounded p-2 font-mono text-xs"
                  {...props}
                >
                  {children}
                </code>
              )
            },
            // Style pre blocks (code block wrapper)
            pre: ({ children }) => (
              <pre className="bg-bg-1 my-2 overflow-x-auto rounded-lg">
                {children}
              </pre>
            ),
            // Style paragraphs
            p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
            // Style links
            a: ({ href, children }) => (
              <a
                href={href}
                className="text-gruvbox-aqua hover:underline"
                target="_blank"
                rel="noopener noreferrer"
              >
                {children}
              </a>
            ),
            // Style lists
            ul: ({ children }) => (
              <ul className="mb-2 list-inside list-disc space-y-1">
                {children}
              </ul>
            ),
            ol: ({ children }) => (
              <ol className="mb-2 list-inside list-decimal space-y-1">
                {children}
              </ol>
            ),
            li: ({ children }) => <li className="text-fg-3">{children}</li>,
            // Style headings
            h1: ({ children }) => (
              <h1 className="text-fg mb-2 text-lg font-bold">{children}</h1>
            ),
            h2: ({ children }) => (
              <h2 className="text-fg mb-2 text-base font-bold">{children}</h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-fg mb-1 text-sm font-bold">{children}</h3>
            ),
            // Style blockquotes
            blockquote: ({ children }) => (
              <blockquote className="border-gruvbox-gray text-fg-4 my-2 border-l-2 pl-3 italic">
                {children}
              </blockquote>
            ),
            // Style strong/emphasis
            strong: ({ children }) => (
              <strong className="text-fg font-semibold">{children}</strong>
            ),
            em: ({ children }) => (
              <em className="text-fg-3 italic">{children}</em>
            ),
            // Style tables (minimal borders)
            table: ({ children }) => (
              <div className="my-2 overflow-x-auto">
                <table className="min-w-full border-collapse text-sm">
                  {children}
                </table>
              </div>
            ),
            thead: ({ children }) => (
              <thead className="border-bg-1 border-b">{children}</thead>
            ),
            tbody: ({ children }) => <tbody>{children}</tbody>,
            tr: ({ children }) => (
              <tr className="border-bg-1 border-b last:border-b-0">
                {children}
              </tr>
            ),
            th: ({ children }) => (
              <th className="text-fg px-3 py-2 text-left font-semibold">
                {children}
              </th>
            ),
            td: ({ children }) => (
              <td className="text-fg-3 px-3 py-2">{children}</td>
            ),
          }}
        >
          {entry.content}
        </ReactMarkdown>
      </div>
    </div>
  )
}

/** Thinking/reasoning entry - collapsible */
function ThinkingMessage({ entry }: { entry: ThinkingEntry }) {
  const [isExpanded, setIsExpanded] = useState(false)

  return (
    <div className="border-gruvbox-gray border-l-2 pl-3">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="text-fg-4 hover:text-fg-3 flex w-full items-center gap-2 text-left text-xs transition-colors"
      >
        <ChevronIcon expanded={isExpanded} />
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
            d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
          />
        </svg>
        <span>Thinking</span>
        <span className="text-fg-4/60">{formatTime(entry.ts)}</span>
      </button>
      {isExpanded && (
        <div className="bg-bg-1 text-fg-4 mt-2 rounded p-2 text-xs leading-relaxed whitespace-pre-wrap">
          {entry.content}
        </div>
      )}
    </div>
  )
}

/** Tool call entry with status indicator */
function ToolMessage({ entry }: { entry: ToolEntry }) {
  const [isExpanded, setIsExpanded] = useState(true)

  const statusIcon = {
    running: (
      <div className="border-gruvbox-yellow h-4 w-4 animate-spin rounded-full border-2 border-t-transparent" />
    ),
    success: (
      <svg
        className="text-gruvbox-green h-4 w-4"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M5 13l4 4L19 7"
        />
      </svg>
    ),
    error: (
      <svg
        className="text-gruvbox-red h-4 w-4"
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
    ),
  }

  const statusColors = {
    running: "border-gruvbox-yellow",
    success: "border-gruvbox-green",
    error: "border-gruvbox-red",
  }

  return (
    <div className={`border-l-2 pl-3 ${statusColors[entry.status]}`}>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="text-fg-4 hover:text-fg-3 flex w-full items-center gap-2 text-left text-xs transition-colors"
      >
        <ChevronIcon expanded={isExpanded} />
        {statusIcon[entry.status]}
        <span className="text-gruvbox-yellow font-mono font-medium">
          {entry.name}
        </span>
        <span className="text-fg-4/60">{formatTime(entry.ts)}</span>
      </button>

      {isExpanded && (
        <div className="mt-2 space-y-2">
          {/* Arguments */}
          {entry.args && (
            <div className="bg-bg-1 rounded p-2">
              <div className="text-fg-4 mb-1 text-[10px] uppercase">Args</div>
              <pre className="text-fg-3 overflow-x-auto text-xs">
                {JSON.stringify(entry.args, null, 2)}
              </pre>
            </div>
          )}

          {/* Result */}
          {entry.result && (
            <div className="bg-bg-1 rounded p-2">
              <div className="text-fg-4 mb-1 text-[10px] uppercase">Result</div>
              <pre className="text-fg-3 max-h-40 overflow-auto text-xs whitespace-pre-wrap">
                {entry.result.length > 1000
                  ? entry.result.slice(0, 1000) + "\n... (truncated)"
                  : entry.result}
              </pre>
            </div>
          )}

          {/* Error */}
          {entry.error && (
            <div className="bg-gruvbox-red/10 rounded p-2">
              <div className="text-gruvbox-red mb-1 text-[10px] uppercase">
                Error
              </div>
              <pre className="text-gruvbox-red text-xs whitespace-pre-wrap">
                {entry.error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/** Session completion entry */
function CompleteMessage({ entry }: { entry: CompleteEntry }) {
  const statusColors = {
    success: "bg-gruvbox-green/10 border-gruvbox-green",
    error: "bg-gruvbox-red/10 border-gruvbox-red",
    timeout: "bg-gruvbox-orange/10 border-gruvbox-orange",
  }

  const statusIcons = {
    success: (
      <svg
        className="text-gruvbox-green h-5 w-5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
    ),
    error: (
      <svg
        className="text-gruvbox-red h-5 w-5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
    ),
    timeout: (
      <svg
        className="text-gruvbox-orange h-5 w-5"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
    ),
  }

  return (
    <div className={`rounded-lg border p-3 ${statusColors[entry.status]}`}>
      <div className="mb-2 flex items-center gap-2">
        {statusIcons[entry.status]}
        <span className="text-fg text-sm font-medium">
          Session{" "}
          {entry.status === "success"
            ? "Completed"
            : entry.status === "error"
              ? "Failed"
              : "Timed Out"}
        </span>
        <span className="text-fg-4 text-xs">{formatTime(entry.ts)}</span>
      </div>
      <div className="text-fg-3 grid grid-cols-3 gap-2 text-xs">
        <div>
          <span className="text-fg-4">Turns:</span> {entry.turns}
        </div>
        <div>
          <span className="text-fg-4">Duration:</span>{" "}
          {formatDuration(entry.duration_ms)}
        </div>
        <div>
          <span className="text-fg-4">Tokens:</span> {entry.total_tokens.in}↓{" "}
          {entry.total_tokens.out}↑
        </div>
      </div>
      {entry.message && (
        <div className="text-fg-4 mt-2 text-xs">{entry.message}</div>
      )}
    </div>
  )
}

// =============================================================================
// Utility Components
// =============================================================================

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={`h-3 w-3 transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M9 5l7 7-7 7"
      />
    </svg>
  )
}

function RefreshButton({
  onClick,
  isRefreshing,
}: {
  onClick: () => void
  isRefreshing: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={isRefreshing}
      className="text-fg-4 hover:bg-bg-1 hover:text-fg rounded p-1 transition-colors disabled:opacity-50"
      title="Refresh dialog"
    >
      <svg
        className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
        />
      </svg>
    </button>
  )
}

function ExportButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="text-fg-4 hover:bg-bg-1 hover:text-fg rounded p-1 transition-colors"
      title="Export dialog as JSONL"
    >
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
          d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
        />
      </svg>
    </button>
  )
}

// =============================================================================
// Utility Functions
// =============================================================================

function formatTime(ts: string): string {
  try {
    const date = new Date(ts)
    return date.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    })
  } catch {
    return ts
  }
}

function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)

  if (hours > 0) {
    return `${hours}h ${minutes % 60}m`
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`
  }
  return `${seconds}s`
}

// =============================================================================
// State Components
// =============================================================================

function EmptyState() {
  return (
    <div className="text-fg-4 flex h-full flex-col items-center justify-center px-4">
      <svg
        className="mb-4 h-12 w-12 opacity-20"
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
      <h3 className="text-fg-3 mb-2 text-sm font-medium">No dialog yet</h3>
      <p className="max-w-xs text-center text-xs">
        When the agent starts working, the conversation will appear here.
      </p>
    </div>
  )
}

function LoadingState() {
  return (
    <div className="text-fg-4 flex h-full flex-col items-center justify-center">
      <div className="border-gruvbox-aqua mb-4 h-8 w-8 animate-spin rounded-full border-2 border-t-transparent" />
      <span className="text-sm">Loading dialog...</span>
    </div>
  )
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="text-fg-4 flex h-full flex-col items-center justify-center px-4">
      <svg
        className="text-gruvbox-red mb-4 h-12 w-12 opacity-40"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
        />
      </svg>
      <div className="text-gruvbox-red mb-2 text-sm">Failed to load dialog</div>
      <div className="max-w-xs text-center text-xs opacity-60">{message}</div>
    </div>
  )
}

// =============================================================================
// Entry Router
// =============================================================================

function DialogEntryComponent({ entry }: { entry: DialogEntry }) {
  switch (entry.type) {
    case "init":
      return <InitMessage entry={entry} />
    case "prompt":
      return <PromptMessage entry={entry} />
    case "message":
      return <AssistantMessage entry={entry} />
    case "thinking":
      return <ThinkingMessage entry={entry} />
    case "tool":
      return <ToolMessage entry={entry} />
    case "complete":
      return <CompleteMessage entry={entry} />
    default:
      return null
  }
}

// =============================================================================
// Main Component
// =============================================================================

/**
 * AgentDialogContent - The panel content for the dock system.
 * No outer wrapper, no resize handle — Dock handles those.
 */
export function AgentDialogContent() {
  // Get all data from unified SDK context (WebSocket-based)
  const {
    isInitializing: sdkInitializing,
    dialogEntries: entries,
    latestDialogSeq: latestSeq,
    isComplete,
    resultAvailable,
    error,
    reconnect,
  } = useSDKDataContext()

  // Loading state - only true during initialization
  const isLoading = sdkInitializing

  // Export dialog as JSONL file
  const exportDialog = useCallback(() => {
    if (entries.length === 0) return

    const jsonl = entries.map((e) => JSON.stringify(e)).join("\n")
    const blob = new Blob([jsonl], { type: "application/x-jsonlines" })
    const url = URL.createObjectURL(blob)

    const a = document.createElement("a")
    a.href = url
    a.download = "dialog.jsonl"
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, [entries])

  // Merge tool entries: combine "running" entry (has args) with completed entry (has result)
  // This prevents showing duplicate entries while preserving both args and result
  const filteredEntries = useMemo(() => {
    // Collect args from "running" entries by tool_id
    const runningArgsMap = new Map<string, Record<string, unknown>>()
    for (const entry of entries) {
      if (entry.type === "tool" && entry.status === "running" && entry.args) {
        runningArgsMap.set(entry.tool_id, entry.args)
      }
    }

    // Collect tool_ids that have a result (success or error)
    const completedToolIds = new Set<string>()
    for (const entry of entries) {
      if (entry.type === "tool" && entry.status !== "running") {
        completedToolIds.add(entry.tool_id)
      }
    }

    // Filter out "running" entries for tools that have completed,
    // and merge args into completed entries
    return entries
      .filter((entry) => {
        if (entry.type === "tool" && entry.status === "running") {
          return !completedToolIds.has(entry.tool_id)
        }
        return true
      })
      .map((entry) => {
        // Merge args from running entry into completed entry
        if (entry.type === "tool" && entry.status !== "running") {
          const args = runningArgsMap.get(entry.tool_id)
          if (args && !entry.args) {
            return { ...entry, args }
          }
        }
        return entry
      })
  }, [entries])

  // Auto-scroll to bottom when new entries arrive
  const scrollRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)

  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [filteredEntries.length, autoScroll])

  // Detect if user has scrolled up (disable auto-scroll)
  const handleScroll = () => {
    if (!scrollRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50
    setAutoScroll(isAtBottom)
  }

  return (
    <>
      {/* Header */}
      <header className="border-border-subtle flex h-12 flex-shrink-0 items-center justify-between border-b px-4">
        <div className="flex items-center gap-2">
          <h2 className="text-fg text-sm font-medium">Agent Dialog</h2>
          {entries.length > 0 && (
            <span className="text-fg-4 text-xs">
              {entries.length} entries
              {isComplete && (
                <span className="text-gruvbox-green ml-1">(done)</span>
              )}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {entries.length > 0 && <ExportButton onClick={exportDialog} />}
          <RefreshButton onClick={reconnect} isRefreshing={false} />
        </div>
      </header>

      {/* Messages container */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="min-h-0 flex-1 overflow-y-auto p-4"
      >
        {isLoading || sdkInitializing ? (
          <LoadingState />
        ) : error && !sdkInitializing ? (
          <ErrorState message={error} />
        ) : filteredEntries.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="flex flex-col gap-4">
            {filteredEntries.map((entry) => (
              <DialogEntryComponent key={entry.seq} entry={entry} />
            ))}
          </div>
        )}
      </div>

      {/* Footer - status bar */}
      <footer className="border-border-subtle flex-shrink-0 border-t px-4 py-2">
        <div className="text-fg-4 flex items-center justify-between text-xs">
          <span>
            {sdkInitializing ? (
              <span className="flex items-center gap-2">
                <span className="bg-gruvbox-aqua h-2 w-2 animate-pulse rounded-full" />
                SDK initializing...
              </span>
            ) : isComplete || resultAvailable ? (
              <span className="text-gruvbox-green">Session complete</span>
            ) : entries.length > 0 ? (
              <span className="flex items-center gap-2">
                <span className="bg-gruvbox-green h-2 w-2 animate-pulse rounded-full" />
                Live
              </span>
            ) : (
              "Waiting for agent..."
            )}
          </span>
          {latestSeq >= 0 && (
            <span className="font-mono opacity-60">seq: {latestSeq}</span>
          )}
        </div>
      </footer>
    </>
  )
}
