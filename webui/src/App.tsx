import { useState, useEffect, useRef, createContext, useContext } from "react"
import { Sidebar } from "./components/layout/Sidebar"
import { ProjectInfoBar } from "./components/layout/ProjectInfoBar"
import { AgentDialogContent } from "./components/layout/AgentPanel"
import { DiffWorkspace } from "./components/layout/DiffWorkspace"
import { FileListView } from "./components/layout/FileListView"
import { AIView } from "./components/layout/AIView"
import {
  TerminalContent,
  type TerminalControls,
} from "./components/layout/TerminalContent"
import { LogsContent } from "./components/layout/LogsContent"
import { LaunchingView } from "./components/layout/LaunchingView"
import { HomePage } from "./components/HomePage"
import { NewPanel, type NewPanelTab } from "./components/modals/NewPanel"
import { SettingsPanel } from "./components/modals/SettingsPanel"
import { ContainerProvider, useContainers } from "./context/ContainerContext"
import { SDKDataProvider } from "./context/SDKDataContext"
import { SettingsProvider, useSettings } from "./context/SettingsContext"
import { LaunchProvider, useLaunchContext } from "./context/LaunchContext"
import { Dock, DockProvider, useDock } from "./components/dock"
import { EvaluationResultPanel } from "./components/dock/EvaluationResultPanel"
import { useResizableRight, useResizableTop } from "./hooks/useResizable"
import { AuthGate } from "./components/AuthGate"
import { useServerInfo } from "./lib/serverInfo"

// =============================================================================
// Contexts for global modals
// =============================================================================

interface NewPanelContextValue {
  openNewPanel: (tab: NewPanelTab) => void
}

const NewPanelContext = createContext<NewPanelContextValue | null>(null)

export function useNewPanel() {
  const context = useContext(NewPanelContext)
  if (!context) {
    throw new Error("useNewPanel must be used within NewPanelProvider")
  }
  return context
}

interface SettingsPanelContextValue {
  openSettings: () => void
}

const SettingsPanelContext = createContext<SettingsPanelContextValue | null>(
  null
)

export function useSettingsPanel() {
  const context = useContext(SettingsPanelContext)
  if (!context) {
    throw new Error(
      "useSettingsPanel must be used within SettingsPanelProvider"
    )
  }
  return context
}

// =============================================================================
// Icons for dock tabs
// =============================================================================

function ChangesIcon() {
  return (
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
        d="M4 6h16M4 12h16M4 18h16"
      />
    </svg>
  )
}

function FilesIcon() {
  return (
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
        d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
      />
    </svg>
  )
}

function AIIcon() {
  return (
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
        d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"
      />
    </svg>
  )
}

function TerminalIcon() {
  return (
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
        d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
      />
    </svg>
  )
}

function LogsIcon() {
  return (
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
        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
      />
    </svg>
  )
}

function EvalIcon() {
  return (
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
        d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"
      />
    </svg>
  )
}

// =============================================================================
// Badge components for bottom dock tabs
// =============================================================================

function LogsBadge({ logCount }: { logCount: number }) {
  const { hasActiveLaunches, allLaunches } = useLaunchContext()

  if (hasActiveLaunches) {
    const launchingCount = allLaunches.filter(
      (e) => e.status.status === "launching"
    ).length
    return (
      <span className="bg-gruvbox-yellow/20 text-gruvbox-yellow rounded-full px-2 py-0.5 text-xs">
        {launchingCount > 1 ? `${launchingCount} Launching` : "Launching"}
      </span>
    )
  }

  const failedCount = allLaunches.filter(
    (e) => e.status.status === "failed"
  ).length
  if (failedCount > 0) {
    return (
      <span className="bg-gruvbox-red/20 text-gruvbox-red rounded-full px-2 py-0.5 text-xs">
        {failedCount} Failed
      </span>
    )
  }

  if (logCount > 0) {
    return (
      <span className="text-fg-4 bg-bg-2 rounded-full px-2 py-0.5 text-xs">
        {logCount}
      </span>
    )
  }

  return null
}

// =============================================================================
// Auto-switch to logs on launch
// =============================================================================

function useAutoSwitchToLogs() {
  const { hasActiveLaunches } = useLaunchContext()
  const { setActivePanel } = useDock()

  useEffect(() => {
    if (hasActiveLaunches) {
      setActivePanel("bottom", "logs")
    }
  }, [hasActiveLaunches, setActivePanel])
}

// =============================================================================
// Container Layout - uses the Dock system
// =============================================================================

function ContainerLayout({ containerId }: { containerId: string }) {
  // Auto-switch bottom dock to logs when launch starts
  useAutoSwitchToLogs()

  // Tab position settings
  const { centerTabPosition, bottomTabPosition } = useSettings()

  // Dock visibility
  const { isDockVisible } = useDock()

  // The server may run with the container terminal switched off
  const { terminal: terminalEnabled } = useServerInfo()

  // Panel resize hooks
  const agentPanel = useResizableRight({
    initialSize: 300,
    minSize: 240,
    maxSize: 1200,
  })

  const terminalPanel = useResizableTop({
    initialSize: 192,
    minSize: 100,
    maxSize: 500,
  })

  // Bottom dock: log count for badge
  const [logCount, setLogCount] = useState(0)
  const terminalControlsRef = useRef<TerminalControls | null>(null)

  // Refit terminal on panel resize
  useEffect(() => {
    if (!terminalPanel.isResizing && terminalControlsRef.current) {
      terminalControlsRef.current.resize()
    }
  }, [terminalPanel.size, terminalPanel.isResizing])

  return (
    <>
      {/* Project info bar */}
      <ProjectInfoBar />

      {/* Main content area - left dock + center dock */}
      <div className="flex min-h-0 flex-1">
        {/* Left dock: Agent dialog */}
        {isDockVisible("left") && (
          <Dock
            id="left"
            tabPosition="hidden"
            resize={{
              edge: "right",
              size: agentPanel.size,
              onResizeStart: agentPanel.startResize,
              isResizing: agentPanel.isResizing,
            }}
            className="border-border-subtle bg-bg border-r"
          >
            <Dock.Panel id="agent-dialog" name="Agent Dialog">
              <AgentDialogContent />
            </Dock.Panel>
          </Dock>
        )}

        {/* Center dock: Changes, Files, AI, Terminal, Evaluation Result */}
        {isDockVisible("center") ? (
          <Dock id="center" tabPosition={centerTabPosition}>
            <Dock.Panel id="changes" name="Changes" icon={<ChangesIcon />}>
              <DiffWorkspace />
            </Dock.Panel>
            <Dock.Panel id="files" name="Files" icon={<FilesIcon />}>
              <FileListView />
            </Dock.Panel>
            <Dock.Panel id="ai" name="AI" icon={<AIIcon />}>
              <AIView containerId={containerId} />
            </Dock.Panel>
            {terminalEnabled && (
              <Dock.Panel id="terminal" name="Terminal" icon={<TerminalIcon />}>
                <TerminalContent containerId={containerId} showToolbar />
              </Dock.Panel>
            )}
            <Dock.Panel
              id="eval-result"
              name="Evaluation Result"
              icon={<EvalIcon />}
            >
              <EvaluationResultPanel />
            </Dock.Panel>
          </Dock>
        ) : (
          <div className="flex-1" />
        )}
      </div>

      {/* Bottom dock: Terminal + Logs */}
      {isDockVisible("bottom") && (
        <Dock
          id="bottom"
          tabPosition={bottomTabPosition}
          resize={{
            edge: "top",
            size: terminalPanel.size,
            onResizeStart: terminalPanel.startResize,
            isResizing: terminalPanel.isResizing,
          }}
          className="border-gruvbox-orange-dim border-t-2"
        >
          {terminalEnabled && (
            <Dock.Panel
              id="terminal-bottom"
              name="Terminal"
              icon={<TerminalIcon />}
            >
              <TerminalContent
                containerId={containerId}
                onReady={(controls) => {
                  terminalControlsRef.current = controls
                }}
                showToolbar
              />
            </Dock.Panel>
          )}
          <Dock.Panel
            id="logs"
            name="Logs"
            icon={<LogsIcon />}
            badge={<LogsBadge logCount={logCount} />}
          >
            <LogsContent
              containerId={containerId}
              onLogCountChange={setLogCount}
            />
          </Dock.Panel>
        </Dock>
      )}
    </>
  )
}

// =============================================================================
// App Content
// =============================================================================

function AppContent() {
  const { activeContainerId, activeLaunchId, currentView } = useContainers()
  const [showNewPanel, setShowNewPanel] = useState(false)
  const [newPanelTab, setNewPanelTab] = useState<NewPanelTab>("attach")
  const [showSettings, setShowSettings] = useState(false)

  const openNewPanel = (tab: NewPanelTab) => {
    setNewPanelTab(tab)
    setShowNewPanel(true)
  }

  const openSettings = () => {
    setShowSettings(true)
  }

  // Sidebar resize
  const sidebar = useResizableRight({
    initialSize: 256,
    minSize: 180,
    maxSize: 400,
  })

  return (
    <NewPanelContext.Provider value={{ openNewPanel }}>
      <SettingsPanelContext.Provider value={{ openSettings }}>
        <div className="bg-bg flex h-screen w-screen overflow-hidden">
          {/* Left sidebar - container tabs */}
          <Sidebar
            width={sidebar.size}
            onResizeStart={sidebar.startResize}
            isResizing={sidebar.isResizing}
          />

          {/* Right side container - content + terminal */}
          <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            {currentView === "container" && activeContainerId ? (
              <SDKDataProvider containerId={activeContainerId}>
                <DockProvider
                  defaultPanels={{
                    left: "agent-dialog",
                    center: "changes",
                    bottom: "logs",
                  }}
                >
                  <ContainerLayout containerId={activeContainerId} />
                </DockProvider>
              </SDKDataProvider>
            ) : currentView === "launching" && activeLaunchId ? (
              <LaunchingView launchId={activeLaunchId} />
            ) : (
              <HomePage />
            )}
          </div>
        </div>

        {/* Global modals */}
        <NewPanel
          isOpen={showNewPanel}
          onClose={() => setShowNewPanel(false)}
          defaultTab={newPanelTab}
        />
        <SettingsPanel
          isOpen={showSettings}
          onClose={() => setShowSettings(false)}
        />
      </SettingsPanelContext.Provider>
    </NewPanelContext.Provider>
  )
}

function App() {
  return (
    <AuthGate>
      <SettingsProvider>
        <LaunchProvider>
          <ContainerProvider>
            <AppContent />
          </ContainerProvider>
        </LaunchProvider>
      </SettingsProvider>
    </AuthGate>
  )
}

export default App
