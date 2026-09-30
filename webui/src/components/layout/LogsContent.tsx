/**
 * Logs Content - Container logs viewer
 *
 * Displays the container's logs, as the runner backend has them.
 * Streams logs in real-time with auto-scroll functionality.
 */

import { useState, useEffect, useRef, useCallback } from "react"
import { useContainerLogs } from "../../hooks/useContainerLogs"

interface LogsContentProps {
  /** Container ID to show logs for */
  containerId: string | null
  /** Callback when log count changes (for parent badge) */
  onLogCountChange?: (count: number) => void
}

export function LogsContent({
  containerId,
  onLogCountChange,
}: LogsContentProps) {
  const [isAtBottom, setIsAtBottom] = useState(true)
  const logsEndRef = useRef<HTMLDivElement>(null)
  const logsContainerRef = useRef<HTMLDivElement>(null)
  const { logs, isConnected, error } = useContainerLogs(containerId)

  // Update parent with log count
  useEffect(() => {
    if (onLogCountChange) {
      onLogCountChange(logs.length)
    }
  }, [logs.length, onLogCountChange])

  // Auto-scroll to bottom when logs update ONLY if user is at bottom
  useEffect(() => {
    if (logsEndRef.current && logs.length > 0 && isAtBottom) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" })
    }
  }, [logs, isAtBottom])

  // Handle scroll to detect if user is at bottom
  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget
    const threshold = 50
    const atBottom = scrollHeight - scrollTop - clientHeight < threshold
    setIsAtBottom(atBottom)
  }, [])

  // Jump to bottom
  const jumpToBottom = useCallback(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" })
      setIsAtBottom(true)
    }
  }, [])

  return (
    <div className="bg-bg-hard flex h-full flex-col">
      {/* Action bar */}
      <div className="border-border-subtle bg-bg-1 flex items-center justify-between border-b px-3 py-2">
        <div className="flex items-center gap-2">
          {containerId && (
            <>
              {isConnected ? (
                <span className="bg-gruvbox-green/20 text-gruvbox-green flex items-center gap-1.5 rounded px-2 py-0.5 text-xs font-medium">
                  <span className="bg-gruvbox-green h-1.5 w-1.5 animate-pulse rounded-full" />
                  Streaming
                </span>
              ) : error ? (
                <span className="bg-gruvbox-red/20 text-gruvbox-red rounded px-2 py-0.5 text-xs font-medium">
                  Error
                </span>
              ) : (
                <span className="bg-gruvbox-yellow/20 text-gruvbox-yellow flex items-center gap-1.5 rounded px-2 py-0.5 text-xs font-medium">
                  <span className="bg-gruvbox-yellow h-1.5 w-1.5 animate-pulse rounded-full" />
                  Connecting
                </span>
              )}
            </>
          )}
          {logs.length > 0 && (
            <span className="text-fg-4 text-xs">
              {logs.length} line{logs.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {!isAtBottom && logs.length > 0 && (
            <button
              onClick={jumpToBottom}
              className="text-fg-4 hover:text-fg flex items-center gap-1 text-xs transition-colors"
              title="Jump to bottom"
            >
              <svg
                className="h-3 w-3"
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
              Bottom
            </button>
          )}
        </div>
      </div>

      {/* Logs container */}
      <div
        ref={logsContainerRef}
        onScroll={handleScroll}
        className="bg-bg-hard flex-1 overflow-y-auto p-3 font-mono text-xs"
      >
        {!containerId ? (
          <div className="text-fg-4 flex h-full flex-col items-center justify-center">
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
                d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"
              />
            </svg>
            <p className="mb-2 text-sm">No container selected</p>
            <p className="text-center text-xs opacity-60">
              Attach to a container to view its logs
            </p>
          </div>
        ) : logs.length === 0 ? (
          <div className="text-fg-4 flex h-full flex-col items-center justify-center">
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
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            <p className="mb-2 text-sm">
              {isConnected
                ? "No logs yet"
                : error
                  ? "Connection error"
                  : "Connecting..."}
            </p>
            <p className="text-center text-xs opacity-60">
              {error || "Waiting for container logs"}
            </p>
          </div>
        ) : (
          <div className="space-y-0.5">
            {logs.map((line, i) => (
              <LogLine key={i} line={line} />
            ))}
            <div ref={logsEndRef} />
          </div>
        )}
      </div>
    </div>
  )
}

// Log line with syntax coloring
function LogLine({ line }: { line: string }) {
  let className = "text-fg-3"

  if (line.includes("[ssebench]")) {
    className = "text-gruvbox-aqua"
  } else if (line.includes("ERROR") || line.includes("error:")) {
    className = "text-gruvbox-red"
  } else if (line.includes("WARNING") || line.includes("warning:")) {
    className = "text-gruvbox-yellow"
  } else if (line.includes("INFO") || line.includes("Starting")) {
    className = "text-gruvbox-green"
  } else if (line.startsWith("#")) {
    // Docker build steps
    className = "text-fg-4"
  }

  return <div className={className}>{line}</div>
}
