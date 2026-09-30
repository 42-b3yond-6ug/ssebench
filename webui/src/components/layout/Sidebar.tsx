/**
 * Left sidebar - Container tabs and navigation
 *
 * Features:
 * - "+" button opens ContainerSelector modal
 * - Container cards with status indicator
 * - Health indicator and settings at bottom
 */

import { useState, useEffect, useCallback, useRef } from "react"
import { useContainers } from "../../context/useContainers"
import { useBackendHealth } from "../../hooks/useBackendHealth"
import { useServerInfo } from "../../lib/serverInfo"
import {
  useLaunchContext,
  type LaunchEntry,
} from "../../context/useLaunchContext"
import { useNewPanel, useSettingsPanel } from "../../context/usePanels"
import { DetachModal } from "../DetachModal"
import { ResizeHandle } from "../ui/ResizeHandle"
import { stopContainer, removeContainer } from "../../lib/api"
import { statusLabel } from "../../lib/runStatus"
import type { DockerContainer } from "../../types/container"

interface SidebarProps {
  width: number
  onResizeStart: (e: React.MouseEvent) => void
  isResizing: boolean
}

export function Sidebar({ width, onResizeStart, isResizing }: SidebarProps) {
  const [containerToDetach, setContainerToDetach] =
    useState<DockerContainer | null>(null)

  const {
    attachedContainers,
    activeContainerId,
    activeLaunchId,
    currentView,
    setActiveContainer,
    attachContainerDirect,
    detachContainer,
    showHome,
    showLaunch,
    refreshContainers,
  } = useContainers()
  const { openNewPanel } = useNewPanel()
  const { isHealthy, runner, backend, error } = useBackendHealth()
  const { terminalHint, readOnly } = useServerInfo()
  const {
    allLaunches,
    cancel: cancelLaunch,
    clear: clearLaunch,
  } = useLaunchContext()

  // Track which launch_ids we've already started auto-attaching
  const attachedLaunchIds = useRef<Set<string>>(new Set())

  // Auto-attach container when any launch transitions to "running".
  // Uses fresh data from refreshContainers() and attachContainerDirect()
  // to avoid stale closure issues.
  useEffect(() => {
    for (const entry of allLaunches) {
      const { status } = entry
      if (
        status.status === "running" &&
        status.containerId &&
        !attachedLaunchIds.current.has(status.launch_id)
      ) {
        attachedLaunchIds.current.add(status.launch_id)
        const launchId = status.launch_id
        const containerId = status.containerId

        // Capture whether user is currently viewing THIS launch's log
        const isViewingThisLaunch =
          currentView === "launching" && activeLaunchId === launchId

        // Refresh to pick up the new container, using returned fresh data
        refreshContainers().then((freshContainers) => {
          const container = freshContainers.find((c) => c.id === containerId)
          if (container) {
            // switchTo=true if user was watching this launch, false otherwise
            attachContainerDirect(container, isViewingThisLaunch)
          }
          // Always clear the launch entry from the sidebar
          clearLaunch(launchId)
        })
      }
    }
  }, [
    allLaunches,
    currentView,
    activeLaunchId,
    refreshContainers,
    attachContainerDirect,
    clearLaunch,
  ])

  const handleDetachClick = (container: DockerContainer) => {
    setContainerToDetach(container)
  }

  const handleDetach = useCallback(() => {
    if (containerToDetach) {
      detachContainer(containerToDetach.id)
      setContainerToDetach(null)
    }
  }, [containerToDetach, detachContainer])

  const handleDetachAndStop = useCallback(async () => {
    if (containerToDetach) {
      try {
        await stopContainer(containerToDetach.id)
        await removeContainer(containerToDetach.id)
      } catch (error) {
        console.error("Failed to stop/remove container:", error)
      }
      detachContainer(containerToDetach.id)
      setContainerToDetach(null)
    }
  }, [containerToDetach, detachContainer])

  const handleDetachCancel = () => {
    setContainerToDetach(null)
  }

  return (
    <>
      <aside
        className="border-border-subtle bg-bg-hard relative flex flex-col border-r"
        style={{ width }}
      >
        {/* Resize handle on right edge */}
        <ResizeHandle
          edge="right"
          onResizeStart={onResizeStart}
          isResizing={isResizing}
        />

        {/* SSEBench Title */}
        <div className="border-border-subtle border-b px-4 py-3">
          <h1 className="text-gruvbox-orange text-lg font-bold">SSEBench</h1>
          <p className="text-fg-4 text-xs">Software Engineering Benchmark</p>

          {/* Backend Status Indicator */}
          <div className="mt-3">
            <HealthIndicator
              isHealthy={isHealthy}
              runner={runner}
              backend={backend}
              error={error}
            />
            {terminalHint && (
              <p className="text-gruvbox-yellow mt-2 text-xs">{terminalHint}</p>
            )}
          </div>
        </div>

        {/* Container list */}
        <div className="flex-1 overflow-y-auto">
          {/* Show launching cards — one per active launch */}
          {allLaunches.length > 0 && (
            <div className="py-2">
              {allLaunches.map((entry) => (
                <LaunchingCard
                  key={entry.status.launch_id}
                  entry={entry}
                  isActive={
                    currentView === "launching" &&
                    activeLaunchId === entry.status.launch_id
                  }
                  onClick={() => showLaunch(entry.status.launch_id)}
                  onCancel={() => cancelLaunch(entry.status.launch_id)}
                  onClear={() => clearLaunch(entry.status.launch_id)}
                />
              ))}
            </div>
          )}

          {attachedContainers.length === 0 && allLaunches.length === 0 ? (
            <div className="text-fg-4 px-4 py-8 text-center text-sm">
              <p className="opacity-60">No containers attached</p>
              <p className="mt-1 text-xs opacity-40">Click + to get started</p>
            </div>
          ) : attachedContainers.length > 0 ? (
            <div className={allLaunches.length > 0 ? "" : "py-2"}>
              {attachedContainers.map((container) => (
                <ContainerCard
                  key={container.id}
                  container={container}
                  isActive={container.id === activeContainerId}
                  onClick={() => setActiveContainer(container.id)}
                  onDetachClick={() => handleDetachClick(container)}
                />
              ))}
            </div>
          ) : null}
        </div>

        {/* Bottom section */}
        <div className="border-border-subtle mt-auto border-t">
          {/* Home button */}
          <button
            onClick={showHome}
            className={`flex w-full items-center gap-2 px-4 py-3 text-sm transition-colors ${
              currentView === "home"
                ? "bg-bg-1 text-gruvbox-aqua"
                : "text-fg-4 hover:bg-bg-1 hover:text-fg"
            }`}
          >
            <HomeIcon />
            <span className="font-medium">Home</span>
          </button>

          {/* Launch button - Opens New Panel (Primary action) */}
          {!readOnly && (
            <button
              onClick={() => openNewPanel("launch")}
              className="text-fg-4 hover:bg-bg-1 hover:text-gruvbox-yellow flex w-full items-center gap-2 px-4 py-3 text-sm transition-colors"
            >
              <RocketIcon />
              <span className="font-medium">Launch New Test</span>
            </button>
          )}

          {/* Attach button - Opens New Panel (Secondary action) */}
          <button
            onClick={() => openNewPanel("attach")}
            className="text-fg-4 hover:bg-bg-1 hover:text-gruvbox-aqua flex w-full items-center gap-2 px-4 py-3 text-sm transition-colors"
          >
            <ContainerIcon />
            <span className="font-medium">
              {readOnly ? "Browse Runs" : "Attach to Container"}
            </span>
          </button>

          {/* Divider */}
          <div className="border-border-subtle border-t" />

          <SettingsButton />
        </div>
      </aside>

      {/* Detach confirmation modal */}
      {containerToDetach && (
        <DetachModal
          container={containerToDetach}
          isOpen={true}
          onDetach={handleDetach}
          onDetachAndStop={handleDetachAndStop}
          onCancel={handleDetachCancel}
        />
      )}
    </>
  )
}

/**
 * Container card with left border status indicator
 */
function ContainerCard({
  container,
  isActive,
  onClick,
  onDetachClick,
}: {
  container: DockerContainer
  isActive: boolean
  onClick: () => void
  onDetachClick: () => void
}) {
  const statusBorderColors = {
    running: "border-l-gruvbox-green",
    exited: "border-l-gruvbox-red",
    paused: "border-l-gruvbox-yellow",
    created: "border-l-gruvbox-blue",
    unknown: "border-l-gruvbox-yellow",
  }

  return (
    <div
      className={`group relative mx-2 my-0.5 cursor-pointer rounded-r border-l-2 transition-all ${
        isActive
          ? "border-l-gruvbox-aqua bg-bg-1"
          : `${statusBorderColors[container.status]} hover:bg-bg-1`
      }`}
      onClick={onClick}
    >
      {/* Main content */}
      <div className="px-3 py-2">
        {/* Top row: Task ID + Status */}
        <div className="flex items-center justify-between gap-2">
          <span
            className={`truncate font-mono text-sm ${
              isActive ? "text-gruvbox-aqua" : "text-gruvbox-yellow"
            }`}
          >
            {container.taskId}
          </span>
          <span
            className={`flex-shrink-0 text-xs ${
              isActive ? "text-gruvbox-aqua/60" : "text-fg-4"
            }`}
          >
            {statusLabel(container, "Stopped")}
          </span>
        </div>

        {/* Bottom row: Model · Agent */}
        <div className="text-fg-4 mt-0.5 flex items-center gap-1 truncate text-xs">
          <span className="truncate">{container.model}</span>
          <span className="opacity-40">·</span>
          <span className="truncate opacity-70">{container.agent}</span>
        </div>
      </div>

      {/* Detach button - top right corner, visible on hover */}
      <button
        onClick={(e) => {
          e.stopPropagation()
          onDetachClick()
        }}
        className="text-fg-4 hover:bg-gruvbox-red/20 hover:text-gruvbox-red absolute top-1 right-1 rounded p-1 opacity-0 transition-all group-hover:opacity-100"
        title="Detach container"
      >
        <CloseIcon />
      </button>
    </div>
  )
}

/**
 * Launching card - shows status of a single launch
 */
function LaunchingCard({
  entry,
  isActive,
  onClick,
  onCancel,
  onClear,
}: {
  entry: LaunchEntry
  isActive?: boolean
  onClick?: () => void
  onCancel: () => Promise<boolean>
  onClear: () => Promise<void>
}) {
  const { status } = entry
  const isLaunching = status.status === "launching"
  const isFailed = status.status === "failed"

  return (
    <div
      onClick={onClick}
      className={`group relative mx-2 my-0.5 cursor-pointer rounded-r border-l-2 transition-all ${
        isActive
          ? "border-l-gruvbox-aqua bg-bg-1"
          : isFailed
            ? "border-l-gruvbox-red bg-gruvbox-red/10 hover:bg-gruvbox-red/15"
            : "border-l-gruvbox-yellow bg-bg-1 hover:bg-bg-2"
      }`}
    >
      {/* Main content */}
      <div className="px-3 py-2">
        {/* Top row: Status label */}
        <div className="flex items-center gap-2">
          {isLaunching && <SpinnerIcon />}
          {isFailed && <ErrorIcon />}
          <span
            className={`text-sm font-medium ${
              isFailed ? "text-gruvbox-red" : "text-gruvbox-yellow"
            }`}
          >
            {isLaunching ? "Launching..." : "Launch Failed"}
          </span>
        </div>

        {/* Task ID */}
        <div className="text-fg-4 mt-0.5 truncate font-mono text-xs">
          {status.taskId}
        </div>

        {/* Error message if failed */}
        {isFailed && status.error && (
          <div className="text-gruvbox-red/80 mt-1 text-xs">{status.error}</div>
        )}
      </div>

      {/* Cancel/Clear button */}
      <button
        onClick={(e) => {
          e.stopPropagation()
          if (isFailed) {
            onClear()
          } else {
            onCancel()
          }
        }}
        className={`absolute top-1 right-1 rounded p-1 opacity-0 transition-all group-hover:opacity-100 ${
          isFailed
            ? "text-fg-4 hover:bg-bg-2 hover:text-fg"
            : "text-fg-4 hover:bg-gruvbox-red/20 hover:text-gruvbox-red"
        }`}
        title={isFailed ? "Dismiss" : "Cancel launch"}
      >
        <CloseIcon />
      </button>
    </div>
  )
}

/**
 * Health indicator
 */
function HealthIndicator({
  isHealthy,
  runner,
  backend,
  error,
}: {
  isHealthy: boolean
  runner: boolean
  backend: string | null
  error: string | null
}) {
  const getTitle = () => {
    if (!isHealthy) return `Backend offline${error ? `: ${error}` : ""}`
    if (!runner) return "Server online, runner unavailable"
    return `Server online, runner backend: ${backend}`
  }

  const getColor = () => {
    if (!isHealthy) return "bg-gruvbox-red"
    if (!runner) return "bg-gruvbox-yellow"
    return "bg-gruvbox-green"
  }

  const getText = () => {
    if (!isHealthy) return "Backend Offline"
    if (!runner) return "Runner Unavailable"
    return "Backend Ready"
  }

  const getBorderColor = () => {
    if (!isHealthy) return "border-gruvbox-red/30"
    if (!runner) return "border-gruvbox-yellow/30"
    return "border-gruvbox-green/30"
  }

  const getBgColor = () => {
    if (!isHealthy) return "bg-gruvbox-red/5"
    if (!runner) return "bg-gruvbox-yellow/5"
    return "bg-gruvbox-green/5"
  }

  return (
    <div
      className={`flex items-center justify-between gap-2 rounded-md border px-3 py-2 text-xs ${getBorderColor()} ${getBgColor()}`}
      title={getTitle()}
    >
      <span className="text-fg-4">{getText()}</span>
      <span className={`h-2 w-2 rounded-full ${getColor()}`} />
    </div>
  )
}

/**
 * Settings button
 */
function SettingsButton() {
  const { openSettings } = useSettingsPanel()

  return (
    <button
      onClick={openSettings}
      className="text-fg-4 hover:bg-bg-1 hover:text-fg flex w-full items-center gap-2 px-4 py-3 text-sm transition-colors"
    >
      <SettingsIcon />
      <span className="font-medium">Settings</span>
    </button>
  )
}

// Icons

function ContainerIcon() {
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
        d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
      />
    </svg>
  )
}

function CloseIcon() {
  return (
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
        d="M6 18L18 6M6 6l12 12"
      />
    </svg>
  )
}

function SettingsIcon() {
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
        d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
      />
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
      />
    </svg>
  )
}

function HomeIcon() {
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
        d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"
      />
    </svg>
  )
}

function RocketIcon() {
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
        d="M13 10V3L4 14h7v7l9-11h-7z"
      />
    </svg>
  )
}

function SpinnerIcon() {
  return (
    <svg
      className="text-gruvbox-yellow h-4 w-4 animate-spin"
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
  )
}

function ErrorIcon() {
  return (
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
        d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
  )
}
