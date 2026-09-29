/**
 * Detach Confirmation Modal
 *
 * Shows a warning before detaching/closing a container tab.
 * Offers two options:
 * - Detach: Just close the tab, container keeps running
 * - Detach + Stop: Close tab, stop and remove the container
 */

import { useState, useEffect, useCallback } from "react"
import type { DockerContainer } from "../types/container"

interface DetachModalProps {
  container: DockerContainer
  isOpen: boolean
  onDetach: () => void
  onDetachAndStop: () => Promise<void>
  onCancel: () => void
}

export function DetachModal({
  container,
  isOpen,
  onDetach,
  onDetachAndStop,
  onCancel,
}: DetachModalProps) {
  const [isStopping, setIsStopping] = useState(false)

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen || isStopping) return
      if (e.key === "Escape") {
        onCancel()
      }
    }

    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [isOpen, isStopping, onCancel])

  // Handle backdrop click
  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget && !isStopping) {
        onCancel()
      }
    },
    [onCancel, isStopping]
  )

  const handleDetachAndStop = useCallback(async () => {
    setIsStopping(true)
    try {
      await onDetachAndStop()
    } finally {
      setIsStopping(false)
    }
  }, [onDetachAndStop])

  if (!isOpen) return null

  const isRunning = container.status === "running"

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={handleBackdropClick}
    >
      <div className="bg-bg border-border-subtle w-full max-w-md rounded-lg border shadow-2xl">
        {/* Header */}
        <div className="border-border-subtle border-b px-4 py-3">
          <h2 className="text-fg text-lg font-semibold">Detach Container?</h2>
        </div>

        {/* Content */}
        <div className="px-4 py-4">
          <p className="text-fg">
            Detaching{" "}
            <span className="text-gruvbox-yellow font-mono">
              {container.taskId}
            </span>
            {container.model !== "unknown" && (
              <span className="text-gruvbox-aqua"> ({container.model})</span>
            )}
          </p>

          {isRunning ? (
            <div className="mt-3 space-y-2">
              <p className="text-fg-4 text-sm">
                <strong className="text-fg">Detach:</strong> Close tab but keep
                container running. You can re-attach later.
              </p>
              <p className="text-fg-4 text-sm">
                <strong className="text-gruvbox-red">Detach + Stop:</strong>{" "}
                Close tab, stop and remove the container. This will terminate
                the SDK daemon and delete the container.
              </p>
            </div>
          ) : (
            <p className="text-fg-4 mt-3 text-sm">
              Container is already stopped. Detaching will close the tab.
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="border-border-subtle flex items-center justify-end gap-3 border-t px-4 py-3">
          <button
            onClick={onCancel}
            disabled={isStopping}
            className="bg-bg-1 border-border-subtle text-fg hover:bg-bg-2 rounded border px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          {isRunning && (
            <button
              onClick={handleDetachAndStop}
              disabled={isStopping}
              className="bg-gruvbox-red text-gruvbox-bg hover:bg-gruvbox-red/80 rounded px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50"
            >
              {isStopping ? "Stopping..." : "Detach + Stop"}
            </button>
          )}
          <button
            onClick={onDetach}
            disabled={isStopping}
            className="bg-gruvbox-aqua text-gruvbox-bg hover:bg-gruvbox-aqua/80 rounded px-4 py-2 text-sm font-medium transition-colors disabled:opacity-50"
          >
            Detach
          </button>
        </div>
      </div>
    </div>
  )
}
