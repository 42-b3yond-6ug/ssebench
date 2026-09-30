/**
 * Base Modal Component
 *
 * Reusable modal wrapper with resizable dimensions, backdrop, and keyboard shortcuts.
 * Provides consistent modal experience across the application.
 */

import { useEffect, useState, useRef, useCallback } from "react"

interface BaseModalProps {
  isOpen: boolean
  onClose: () => void
  children: React.ReactNode
  defaultWidth?: number
  defaultHeight?: number
  minWidth?: number
  minHeight?: number
  maxWidth?: number
  maxHeight?: number
}

export function BaseModal({
  isOpen,
  onClose,
  children,
  defaultWidth = 1200,
  defaultHeight = 750,
  minWidth = 800,
  minHeight = 500,
  maxWidth,
  maxHeight,
}: BaseModalProps) {
  const [size, setSize] = useState({
    width: defaultWidth,
    height: defaultHeight,
  })
  const [isResizing, setIsResizing] = useState(false)
  const modalRef = useRef<HTMLDivElement>(null)
  const resizeStartRef = useRef({ x: 0, y: 0, width: 0, height: 0, edge: "" })

  // Calculate max dimensions based on viewport
  const viewportMaxWidth = maxWidth ?? window.innerWidth * 0.95
  const viewportMaxHeight = maxHeight ?? window.innerHeight * 0.9

  // Reset size each time the modal opens
  const [wasOpen, setWasOpen] = useState(isOpen)
  if (isOpen !== wasOpen) {
    setWasOpen(isOpen)
    if (isOpen) setSize({ width: defaultWidth, height: defaultHeight })
  }

  // Handle escape key
  useEffect(() => {
    if (!isOpen) return

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isResizing) {
        onClose()
      }
    }

    document.addEventListener("keydown", handleEscape)
    return () => document.removeEventListener("keydown", handleEscape)
  }, [isOpen, onClose, isResizing])

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden"
    } else {
      document.body.style.overflow = ""
    }
    return () => {
      document.body.style.overflow = ""
    }
  }, [isOpen])

  // Resize handlers
  const startResize = useCallback(
    (e: React.MouseEvent, edge: string) => {
      e.preventDefault()
      e.stopPropagation()

      setIsResizing(true)
      resizeStartRef.current = {
        x: e.clientX,
        y: e.clientY,
        width: size.width,
        height: size.height,
        edge,
      }
    },
    [size]
  )

  useEffect(() => {
    if (!isResizing) return

    const handleMouseMove = (e: MouseEvent) => {
      const { x, y, width, height, edge } = resizeStartRef.current
      const deltaX = e.clientX - x
      const deltaY = e.clientY - y

      let newWidth = width
      let newHeight = height

      // Calculate new dimensions based on edge
      if (edge.includes("right")) {
        newWidth = width + deltaX
      } else if (edge.includes("left")) {
        newWidth = width - deltaX
      }

      if (edge.includes("bottom")) {
        newHeight = height + deltaY
      } else if (edge.includes("top")) {
        newHeight = height - deltaY
      }

      // Apply constraints
      newWidth = Math.max(minWidth, Math.min(newWidth, viewportMaxWidth))
      newHeight = Math.max(minHeight, Math.min(newHeight, viewportMaxHeight))

      setSize({ width: newWidth, height: newHeight })
    }

    const handleMouseUp = () => {
      setIsResizing(false)
    }

    document.addEventListener("mousemove", handleMouseMove)
    document.addEventListener("mouseup", handleMouseUp)

    return () => {
      document.removeEventListener("mousemove", handleMouseMove)
      document.removeEventListener("mouseup", handleMouseUp)
    }
  }, [isResizing, minWidth, minHeight, viewportMaxWidth, viewportMaxHeight])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* Modal panel */}
      <div
        ref={modalRef}
        className="bg-bg border-border-subtle relative rounded-xl border shadow-2xl transition-shadow"
        style={{
          width: `${size.width}px`,
          height: `${size.height}px`,
          maxWidth: `${viewportMaxWidth}px`,
          maxHeight: `${viewportMaxHeight}px`,
        }}
      >
        {children}

        {/* Resize handles */}
        {/* Top */}
        <div
          className="absolute top-0 right-0 left-0 h-1 cursor-n-resize"
          onMouseDown={(e) => startResize(e, "top")}
        />

        {/* Right */}
        <div
          className="absolute top-0 right-0 bottom-0 w-1 cursor-e-resize"
          onMouseDown={(e) => startResize(e, "right")}
        />

        {/* Bottom */}
        <div
          className="absolute right-0 bottom-0 left-0 h-1 cursor-s-resize"
          onMouseDown={(e) => startResize(e, "bottom")}
        />

        {/* Left */}
        <div
          className="absolute top-0 bottom-0 left-0 w-1 cursor-w-resize"
          onMouseDown={(e) => startResize(e, "left")}
        />

        {/* Corner handles for better UX */}
        {/* Top-left */}
        <div
          className="absolute top-0 left-0 h-3 w-3 cursor-nw-resize"
          onMouseDown={(e) => startResize(e, "top-left")}
        />

        {/* Top-right */}
        <div
          className="absolute top-0 right-0 h-3 w-3 cursor-ne-resize"
          onMouseDown={(e) => startResize(e, "top-right")}
        />

        {/* Bottom-left */}
        <div
          className="absolute bottom-0 left-0 h-3 w-3 cursor-sw-resize"
          onMouseDown={(e) => startResize(e, "bottom-left")}
        />

        {/* Bottom-right */}
        <div
          className="absolute right-0 bottom-0 h-3 w-3 cursor-se-resize"
          onMouseDown={(e) => startResize(e, "bottom-right")}
        />

        {/* Visual resize indicator in bottom-right corner */}
        <div className="pointer-events-none absolute right-1 bottom-1 flex flex-col gap-0.5 opacity-30">
          <div className="flex gap-0.5">
            <div className="bg-fg-4 h-0.5 w-0.5 rounded-full" />
            <div className="bg-fg-4 h-0.5 w-0.5 rounded-full" />
          </div>
          <div className="flex gap-0.5">
            <div className="bg-fg-4 h-0.5 w-0.5 rounded-full" />
            <div className="bg-fg-4 h-0.5 w-0.5 rounded-full" />
          </div>
        </div>
      </div>
    </div>
  )
}
