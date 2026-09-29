import { useState, useCallback, useEffect } from "react"

type Direction = "horizontal" | "vertical"

interface UseResizableOptions {
  direction: Direction
  initialSize: number
  minSize?: number
  maxSize?: number
}

interface UseResizableReturn {
  size: number
  isResizing: boolean
  startResize: (e: React.MouseEvent) => void
}

function useResizable({
  direction,
  initialSize,
  minSize = 100,
  maxSize = 800,
}: UseResizableOptions): UseResizableReturn {
  const [size, setSize] = useState(initialSize)
  const [isResizing, setIsResizing] = useState(false)
  const [startPos, setStartPos] = useState(0)
  const [startSize, setStartSize] = useState(0)

  const startResize = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      setIsResizing(true)
      setStartPos(direction === "horizontal" ? e.clientX : e.clientY)
      setStartSize(size)
    },
    [direction, size]
  )

  useEffect(() => {
    if (!isResizing) return

    const handleMouseMove = (e: MouseEvent) => {
      const currentPos = direction === "horizontal" ? e.clientX : e.clientY
      const delta = currentPos - startPos
      const newSize = Math.min(maxSize, Math.max(minSize, startSize + delta))
      setSize(newSize)
    }

    const handleMouseUp = () => {
      setIsResizing(false)
    }

    document.addEventListener("mousemove", handleMouseMove)
    document.addEventListener("mouseup", handleMouseUp)

    // Add a class to body to prevent text selection during resize
    document.body.style.cursor =
      direction === "horizontal" ? "col-resize" : "row-resize"
    document.body.style.userSelect = "none"

    return () => {
      document.removeEventListener("mousemove", handleMouseMove)
      document.removeEventListener("mouseup", handleMouseUp)
      document.body.style.cursor = ""
      document.body.style.userSelect = ""
    }
  }, [isResizing, direction, startPos, startSize, minSize, maxSize])

  return { size, isResizing, startResize }
}

// Hook for resize from the right/bottom edge (size increases when moving right/down)
export function useResizableRight(
  options: Omit<UseResizableOptions, "direction">
) {
  return useResizable({ ...options, direction: "horizontal" })
}

// Hook for resize from the top edge (size increases when moving up)
export function useResizableTop({
  initialSize,
  minSize = 100,
  maxSize = 600,
}: Omit<UseResizableOptions, "direction">): UseResizableReturn {
  const [size, setSize] = useState(initialSize)
  const [isResizing, setIsResizing] = useState(false)
  const [startPos, setStartPos] = useState(0)
  const [startSize, setStartSize] = useState(0)

  const startResize = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      setIsResizing(true)
      setStartPos(e.clientY)
      setStartSize(size)
    },
    [size]
  )

  useEffect(() => {
    if (!isResizing) return

    const handleMouseMove = (e: MouseEvent) => {
      const delta = startPos - e.clientY // Inverted for top-edge resize
      const newSize = Math.min(maxSize, Math.max(minSize, startSize + delta))
      setSize(newSize)
    }

    const handleMouseUp = () => {
      setIsResizing(false)
    }

    document.addEventListener("mousemove", handleMouseMove)
    document.addEventListener("mouseup", handleMouseUp)

    document.body.style.cursor = "row-resize"
    document.body.style.userSelect = "none"

    return () => {
      document.removeEventListener("mousemove", handleMouseMove)
      document.removeEventListener("mouseup", handleMouseUp)
      document.body.style.cursor = ""
      document.body.style.userSelect = ""
    }
  }, [isResizing, startPos, startSize, minSize, maxSize])

  return { size, isResizing, startResize }
}
