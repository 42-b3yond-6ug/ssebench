/**
 * Terminal Content - Interactive PTY terminal (extracted from TerminalPanel)
 *
 * Pure terminal component without chrome/header, for use in tabbed BottomPanel.
 * Uses xterm.js for terminal emulation and WebSocket for PTY communication.
 */

import { useEffect, useRef, useState, useCallback } from "react"
import { Terminal } from "@xterm/xterm"
import { FitAddon } from "@xterm/addon-fit"
import { SearchAddon } from "@xterm/addon-search"
import "@xterm/xterm/css/xterm.css"
import { getWsBaseUrl } from "../../lib/api"
import { useSettings } from "../../context/SettingsContext"

type ConnectionState = "connecting" | "connected" | "disconnected" | "error"

interface TerminalContentProps {
  containerId: string
  /** Callback when connection state changes (for parent tab indicator) */
  onConnectionStateChange?: (state: ConnectionState) => void
  /** Callback to expose control functions to parent */
  onReady?: (controls: TerminalControls) => void
  /** Show an inline toolbar with font size, search, clear, restart buttons */
  showToolbar?: boolean
}

export interface TerminalControls {
  clear: () => void
  restart: () => void
  resize: () => void
  increaseFontSize: () => void
  decreaseFontSize: () => void
  openSearch: () => void
}

// Message types (must match server)
interface ServerMessage {
  type: "output" | "error" | "exit"
  data?: string
  message?: string
  code?: number | null
}

interface ClientMessage {
  type: "input" | "resize"
  data?: string
  cols?: number
  rows?: number
}

export function TerminalContent({
  containerId,
  onConnectionStateChange,
  onReady,
  showToolbar = false,
}: TerminalContentProps) {
  const terminalRef = useRef<HTMLDivElement>(null)
  const terminalInstance = useRef<Terminal | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const searchAddonRef = useRef<SearchAddon | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  const { getTerminalTheme, terminalTheme } = useSettings()

  const [connectionState, setConnectionState] =
    useState<ConnectionState>("disconnected")
  const [restartCounter, setRestartCounter] = useState(0)
  const [fontSize, setFontSize] = useState(14)
  const [searchVisible, setSearchVisible] = useState(false)
  const [searchTerm, setSearchTerm] = useState("")

  // Notify parent of connection state changes
  useEffect(() => {
    if (onConnectionStateChange) {
      onConnectionStateChange(connectionState)
    }
  }, [connectionState, onConnectionStateChange])

  // Send message to WebSocket
  const sendMessage = useCallback((msg: ClientMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
    }
  }, [])

  // Handle terminal resize
  const handleResize = useCallback(() => {
    if (fitAddonRef.current && terminalInstance.current) {
      fitAddonRef.current.fit()
      const { cols, rows } = terminalInstance.current
      sendMessage({ type: "resize", cols, rows })
    }
  }, [sendMessage])

  // Clear terminal
  const handleClear = useCallback(() => {
    terminalInstance.current?.clear()
  }, [])

  // Restart terminal (reconnect)
  const handleRestart = useCallback(() => {
    // Close existing connection
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    // Clear terminal
    terminalInstance.current?.clear()
    // Trigger reconnect by incrementing counter
    setConnectionState("disconnected")
    setRestartCounter((prev) => prev + 1)
  }, [])

  // Increase font size
  const handleIncreaseFontSize = useCallback(() => {
    setFontSize((prev) => Math.min(prev + 1, 24))
  }, [])

  // Decrease font size
  const handleDecreaseFontSize = useCallback(() => {
    setFontSize((prev) => Math.max(prev - 1, 8))
  }, [])

  // Open search
  const handleOpenSearch = useCallback(() => {
    setSearchVisible((prev) => !prev)
    setSearchTerm("")
  }, [])

  // Handle search input change
  const handleSearchChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const term = e.target.value
      setSearchTerm(term)
      if (term && searchAddonRef.current) {
        searchAddonRef.current.findNext(term, {
          incremental: true,
          caseSensitive: false,
        })
      }
    },
    []
  )

  // Handle search navigation
  const handleSearchPrevious = useCallback(() => {
    if (searchTerm && searchAddonRef.current) {
      searchAddonRef.current.findPrevious(searchTerm, {
        caseSensitive: false,
      })
    }
  }, [searchTerm])

  const handleSearchNext = useCallback(() => {
    if (searchTerm && searchAddonRef.current) {
      searchAddonRef.current.findNext(searchTerm, {
        caseSensitive: false,
      })
    }
  }, [searchTerm])

  // Update terminal font size when it changes
  useEffect(() => {
    if (terminalInstance.current && fitAddonRef.current) {
      terminalInstance.current.options.fontSize = fontSize
      // Re-fit after font size change
      setTimeout(() => {
        fitAddonRef.current?.fit()
      }, 0)
    }
  }, [fontSize])

  // Update terminal theme when it changes
  useEffect(() => {
    if (terminalInstance.current) {
      terminalInstance.current.options.theme = getTerminalTheme()
    }
  }, [terminalTheme, getTerminalTheme])

  // Expose controls to parent
  useEffect(() => {
    if (onReady) {
      onReady({
        clear: handleClear,
        restart: handleRestart,
        resize: handleResize,
        increaseFontSize: handleIncreaseFontSize,
        decreaseFontSize: handleDecreaseFontSize,
        openSearch: handleOpenSearch,
      })
    }
  }, [
    onReady,
    handleClear,
    handleRestart,
    handleResize,
    handleIncreaseFontSize,
    handleDecreaseFontSize,
    handleOpenSearch,
  ])

  // Initialize terminal and connect to WebSocket
  useEffect(() => {
    if (!terminalRef.current || !containerId) return

    // Create terminal instance
    const terminal = new Terminal({
      cursorBlink: true,
      cursorStyle: "bar",
      fontSize: fontSize,
      fontFamily:
        '"JetBrainsMono Nerd Font", "JetBrains Mono", "Fira Code", "SF Mono", Menlo, Monaco, monospace',
      theme: getTerminalTheme(),
      scrollback: 10000,
      convertEol: true,
    })

    // Create fit addon
    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)

    // Create search addon
    const searchAddon = new SearchAddon()
    terminal.loadAddon(searchAddon)

    // Mount terminal
    terminal.open(terminalRef.current)
    fitAddon.fit()

    terminalInstance.current = terminal
    fitAddonRef.current = fitAddon
    searchAddonRef.current = searchAddon

    // Connect to WebSocket (Bun backend on port 3001)
    const wsUrl = `${getWsBaseUrl()}/api/pty/${containerId}`
    setConnectionState("connecting")

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setConnectionState("connected")
      // Send initial resize
      const { cols, rows } = terminal
      sendMessage({ type: "resize", cols, rows })
    }

    ws.onmessage = (event) => {
      try {
        const msg: ServerMessage = JSON.parse(event.data)

        switch (msg.type) {
          case "output":
            if (msg.data) {
              terminal.write(msg.data)
            }
            break
          case "error":
            setConnectionState("error")
            terminal.writeln(`\r\n\x1b[31mError: ${msg.message}\x1b[0m`)
            break
          case "exit":
            terminal.writeln(
              `\r\n\x1b[33mProcess exited with code ${msg.code}\x1b[0m`
            )
            setConnectionState("disconnected")
            break
        }
      } catch {
        // If not JSON, treat as raw output (shouldn't happen)
        terminal.write(event.data)
      }
    }

    ws.onerror = () => {
      setConnectionState("error")
    }

    ws.onclose = (event) => {
      if (event.wasClean) {
        setConnectionState("disconnected")
      } else {
        setConnectionState((prev) => (prev === "error" ? prev : "disconnected"))
      }
    }

    // Handle terminal input
    const inputDisposable = terminal.onData((data) => {
      sendMessage({ type: "input", data })
    })

    // Handle terminal resize events
    const resizeDisposable = terminal.onResize(({ cols, rows }) => {
      sendMessage({ type: "resize", cols, rows })
    })

    // Setup ResizeObserver for container size changes
    const resizeObserver = new ResizeObserver(() => {
      requestAnimationFrame(() => {
        fitAddon.fit()
      })
    })
    resizeObserver.observe(terminalRef.current)

    // Cleanup
    return () => {
      inputDisposable.dispose()
      resizeDisposable.dispose()
      resizeObserver.disconnect()
      ws.close()
      terminal.dispose()
      terminalInstance.current = null
      fitAddonRef.current = null
      searchAddonRef.current = null
      wsRef.current = null
    }
  }, [containerId, sendMessage, restartCounter, fontSize])

  return (
    <div className="flex h-full w-full flex-col">
      {/* Optional inline toolbar */}
      {showToolbar && (
        <div className="border-border-subtle flex flex-shrink-0 items-center gap-1 border-b px-3 py-1">
          {/* Font size controls */}
          <button
            onClick={handleDecreaseFontSize}
            className="text-fg-4 hover:text-gruvbox-orange hover:bg-gruvbox-orange/10 rounded px-2 py-1 text-xs transition-colors"
            title="Decrease font size"
          >
            A−
          </button>
          <button
            onClick={handleIncreaseFontSize}
            className="text-fg-4 hover:text-gruvbox-orange hover:bg-gruvbox-orange/10 rounded px-2 py-1 text-xs transition-colors"
            title="Increase font size"
          >
            A+
          </button>

          {/* Divider */}
          <div className="bg-border-subtle mx-1 h-4 w-px" />

          {/* Search */}
          <button
            onClick={handleOpenSearch}
            className="text-fg-4 hover:text-gruvbox-orange hover:bg-gruvbox-orange/10 rounded px-2 py-1 text-xs transition-colors"
            title="Search in terminal"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.35-4.35" />
            </svg>
          </button>

          {/* Divider */}
          <div className="bg-border-subtle mx-1 h-4 w-px" />

          {/* Clear and Restart */}
          <button
            onClick={handleClear}
            className="text-fg-4 hover:text-gruvbox-orange hover:bg-gruvbox-orange/10 rounded px-2 py-1 text-xs transition-colors"
            title="Clear terminal"
          >
            Clear
          </button>
          <button
            onClick={handleRestart}
            className="text-fg-4 hover:text-gruvbox-orange hover:bg-gruvbox-orange/10 rounded px-2 py-1 text-xs transition-colors"
            title="Restart terminal"
          >
            Restart
          </button>
        </div>
      )}

      {/* Terminal area */}
      <div className="relative min-h-0 flex-1">
        {/* Search bar */}
        {searchVisible && (
          <div className="bg-bg-1 border-border absolute top-4 right-4 z-10 flex items-center gap-2 rounded border p-2 shadow-lg">
            <input
              type="text"
              value={searchTerm}
              onChange={handleSearchChange}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  setSearchVisible(false)
                } else if (e.key === "Enter") {
                  if (e.shiftKey) {
                    handleSearchPrevious()
                  } else {
                    handleSearchNext()
                  }
                }
              }}
              placeholder="Find in terminal..."
              className="bg-bg text-fg placeholder:text-fg-4 focus:ring-gruvbox-orange w-48 rounded border-none px-2 py-1 text-sm outline-none focus:ring-1"
              autoFocus
            />
            <button
              onClick={handleSearchPrevious}
              className="text-fg-4 hover:text-fg px-2 text-sm"
              title="Previous match (Shift+Enter)"
            >
              ↑
            </button>
            <button
              onClick={handleSearchNext}
              className="text-fg-4 hover:text-fg px-2 text-sm"
              title="Next match (Enter)"
            >
              ↓
            </button>
            <button
              onClick={() => setSearchVisible(false)}
              className="text-fg-4 hover:text-fg px-2 text-sm"
              title="Close (Esc)"
            >
              ✕
            </button>
          </div>
        )}

        {/* Terminal */}
        <div
          ref={terminalRef}
          className="terminal-container h-full w-full overflow-hidden p-4"
          style={{ backgroundColor: getTerminalTheme().background }}
        />
      </div>
    </div>
  )
}
