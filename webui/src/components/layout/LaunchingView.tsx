/**
 * LaunchingView — Full-screen log viewer for a launching task.
 *
 * Displayed when the user clicks a launching card in the sidebar.
 * Shows the build/launch logs streamed via LaunchContext, with
 * status indicator, cancel button, and auto-scroll.
 */

import { useState, useEffect, useCallback, useRef } from "react"
import { useLaunchContext } from "../../context/useLaunchContext"

interface LaunchingViewProps {
  launchId: string
}

export function LaunchingView({ launchId }: LaunchingViewProps) {
  const { getLaunch, cancel, clear } = useLaunchContext()
  const entry = getLaunch(launchId)

  const [isAtBottom, setIsAtBottom] = useState(true)
  const logsEndRef = useRef<HTMLDivElement>(null)

  const logs = entry?.logs ?? []
  const status = entry?.status

  // Auto-scroll to bottom
  useEffect(() => {
    if (logsEndRef.current && logs.length > 0 && isAtBottom) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" })
    }
  }, [logs.length, isAtBottom])

  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget
    const threshold = 50
    setIsAtBottom(scrollHeight - scrollTop - clientHeight < threshold)
  }, [])

  const jumpToBottom = useCallback(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" })
      setIsAtBottom(true)
    }
  }, [])

  const handleCancel = useCallback(() => {
    cancel(launchId)
  }, [cancel, launchId])

  const handleClear = useCallback(() => {
    clear(launchId)
  }, [clear, launchId])

  if (!entry) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-fg-4 text-center">
          <p className="text-lg">Launch not found</p>
          <p className="mt-1 text-sm opacity-60">
            This launch may have been cleared.
          </p>
        </div>
      </div>
    )
  }

  const isLaunching = status?.status === "launching"
  const isFailed = status?.status === "failed"
  const isRunning = status?.status === "running"

  return (
    <div className="flex h-full flex-col">
      {/* Header bar */}
      <div className="border-border-subtle bg-bg-1 flex items-center justify-between border-b px-6 py-4">
        <div className="flex items-center gap-4">
          {/* Status indicator */}
          {isLaunching && (
            <span className="bg-gruvbox-yellow/20 text-gruvbox-yellow flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium">
              <svg
                className="h-4 w-4 animate-spin"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              Launching
            </span>
          )}
          {isRunning && (
            <span className="bg-gruvbox-green/20 text-gruvbox-green flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium">
              <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                  clipRule="evenodd"
                />
              </svg>
              Running
            </span>
          )}
          {isFailed && (
            <span className="bg-gruvbox-red/20 text-gruvbox-red flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium">
              <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                  clipRule="evenodd"
                />
              </svg>
              Failed
            </span>
          )}

          {/* Task info */}
          <div>
            <span className="text-gruvbox-yellow font-mono text-sm font-medium">
              {status?.taskId}
            </span>
            <span className="text-fg-4 ml-3 text-xs">
              {status?.startTime
                ? new Date(status.startTime).toLocaleTimeString()
                : ""}
            </span>
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          {isLaunching && (
            <button
              onClick={handleCancel}
              className="text-gruvbox-red hover:bg-gruvbox-red/10 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors"
            >
              Cancel
            </button>
          )}
          {isFailed && (
            <button
              onClick={handleClear}
              className="text-fg-4 hover:bg-bg-2 hover:text-fg rounded-lg px-3 py-1.5 text-sm font-medium transition-colors"
            >
              Dismiss
            </button>
          )}
        </div>
      </div>

      {/* Command preview */}
      {status?.command && (
        <div className="bg-bg-hard border-border-subtle border-b px-6 py-2">
          <code className="text-fg-4 font-mono text-xs">{status.command}</code>
        </div>
      )}

      {/* Logs area */}
      <div className="relative min-h-0 flex-1">
        <div
          onScroll={handleScroll}
          className="bg-bg-hard h-full overflow-y-auto p-6 font-mono text-sm"
        >
          {logs.length === 0 ? (
            <div className="text-fg-4 flex h-full items-center justify-center">
              <div className="text-center">
                <svg
                  className="mx-auto mb-3 h-12 w-12 opacity-50"
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
                <p>Waiting for logs...</p>
              </div>
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

        {/* Jump to bottom button */}
        {!isAtBottom && logs.length > 0 && (
          <button
            onClick={jumpToBottom}
            className="bg-gruvbox-aqua text-bg-hard hover:bg-gruvbox-aqua/90 absolute right-6 bottom-6 rounded-full px-4 py-2 text-sm font-medium shadow-lg transition-colors"
          >
            Jump to Bottom
          </button>
        )}
      </div>

      {/* Error details footer */}
      {isFailed && status?.error && (
        <div className="bg-gruvbox-red/10 border-gruvbox-red/20 border-t px-6 py-3">
          <p className="text-gruvbox-red text-sm font-medium">Error</p>
          <p className="text-gruvbox-red/80 mt-0.5 text-sm">{status.error}</p>
        </div>
      )}
    </div>
  )
}

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
    className = "text-fg-4"
  }

  return <div className={className}>{line}</div>
}
