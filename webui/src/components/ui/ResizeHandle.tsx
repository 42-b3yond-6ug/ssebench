/**
 * ResizeHandle - Draggable edge for resizable panels
 *
 * Renders an invisible hit area that shows a visual indicator on hover.
 * Supports horizontal (left/right edges) and vertical (top/bottom edges) resize.
 */

import { useCallback } from "react"

type Edge = "left" | "right" | "top" | "bottom"

interface ResizeHandleProps {
  edge: Edge
  onResizeStart: (e: React.MouseEvent) => void
  isResizing?: boolean
}

export function ResizeHandle({
  edge,
  onResizeStart,
  isResizing,
}: ResizeHandleProps) {
  const isHorizontal = edge === "left" || edge === "right"

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      onResizeStart(e)
    },
    [onResizeStart]
  )

  const positionClasses = {
    left: "left-0 top-0 bottom-0 -translate-x-1/2",
    right: "right-0 top-0 bottom-0 translate-x-1/2",
    top: "top-0 left-0 right-0 -translate-y-1/2",
    bottom: "bottom-0 left-0 right-0 translate-y-1/2",
  }

  const sizeClasses = isHorizontal
    ? "w-2 cursor-col-resize"
    : "h-2 cursor-row-resize"

  const indicatorClasses = isHorizontal
    ? "w-0.5 h-8 rounded-full"
    : "h-0.5 w-8 rounded-full"

  return (
    <div
      className={`group absolute z-10 flex items-center justify-center ${positionClasses[edge]} ${sizeClasses}`}
      onMouseDown={handleMouseDown}
    >
      {/* Visual indicator - shows on hover or during resize */}
      <div
        className={`${indicatorClasses} transition-colors ${
          isResizing ? "bg-gruvbox-aqua" : "group-hover:bg-fg-4 bg-transparent"
        }`}
      />
    </div>
  )
}
