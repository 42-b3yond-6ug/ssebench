/**
 * Attach Content - Container selector for New panel
 *
 * Shows filterable list of containers with tab-based filtering by status.
 */

import { useState, useMemo, useCallback } from "react"
import { useContainers } from "../../context/useContainers"
import type { DockerContainer } from "../../types/container"
import { removeContainer } from "../../lib/api"
import { useServerInfo } from "../../lib/serverInfo"
import { statusLabel } from "../../lib/runStatus"

interface AttachContentProps {
  onAttach: (id: string) => void
  onAttachAll: (ids: string[]) => void
}

type FilterTab = "running" | "exited" | "all" | "recent"

export function AttachContent({ onAttach, onAttachAll }: AttachContentProps) {
  const {
    containers,
    isLoading,
    error,
    refreshContainers,
    isAttached,
    getRecentContainers,
  } = useContainers()

  const { readOnly } = useServerInfo()

  // A read-only server has runs to browse, not to watch
  const [activeTab, setActiveTab] = useState<FilterTab>(
    readOnly ? "all" : "running"
  )
  const [search, setSearch] = useState("")
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [removeError, setRemoveError] = useState<string | null>(null)

  // Get containers based on active tab
  const tabContainers = useMemo(() => {
    if (activeTab === "recent") {
      return getRecentContainers()
    }

    if (activeTab === "running") {
      return containers.filter((c) => c.status === "running")
    }

    if (activeTab === "exited") {
      return containers.filter((c) => c.status === "exited")
    }

    return containers // "all"
  }, [activeTab, containers, getRecentContainers])

  // Filter by search
  const filteredContainers = useMemo(() => {
    if (!search) return tabContainers

    const searchLower = search.toLowerCase()
    return tabContainers.filter((c) => {
      return (
        c.name.toLowerCase().includes(searchLower) ||
        c.taskId.toLowerCase().includes(searchLower) ||
        c.model.toLowerCase().includes(searchLower) ||
        c.agent.toLowerCase().includes(searchLower) ||
        c.image.toLowerCase().includes(searchLower)
      )
    })
  }, [tabContainers, search])

  // Count containers by status
  const counts = useMemo(() => {
    return {
      running: containers.filter((c) => c.status === "running").length,
      exited: containers.filter((c) => c.status === "exited").length,
      all: containers.length,
      recent: getRecentContainers().length,
    }
  }, [containers, getRecentContainers])

  // Attach all acts on what the tab and the search show
  const unattachedIds = useMemo(
    () => filteredContainers.filter((c) => !isAttached(c.id)).map((c) => c.id),
    [filteredContainers, isAttached]
  )

  const selected = containers.find((c) => c.id === selectedId)
  // Only a container that has stopped is offered for removal here
  const canRemove =
    !readOnly &&
    selected?.source === "container" &&
    selected.status === "exited" &&
    !isAttached(selected.id)

  const handleRemove = useCallback(async () => {
    if (!selectedId) return
    setRemoveError(null)
    try {
      await removeContainer(selectedId)
      setSelectedId(null)
      await refreshContainers()
    } catch (err) {
      setRemoveError(
        err instanceof Error ? err.message : "Failed to remove the container"
      )
    }
  }, [selectedId, refreshContainers])

  const handleAttach = useCallback(() => {
    if (selectedId) {
      onAttach(selectedId)
    }
  }, [selectedId, onAttach])

  const handleAttachAll = useCallback(() => {
    onAttachAll(unattachedIds)
  }, [unattachedIds, onAttachAll])

  const handleRowClick = useCallback((container: DockerContainer) => {
    setSelectedId(container.id)
  }, [])

  const handleRowDoubleClick = useCallback(
    (container: DockerContainer) => {
      onAttach(container.id)
    },
    [onAttach]
  )

  return (
    <div className="flex h-full flex-col">
      {/* Header - Search and Refresh */}
      <div className="border-border-subtle flex items-center gap-3 border-b px-4 py-3">
        <div className="relative flex-1">
          <svg
            className="text-fg-4 absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by task ID, model, agent..."
            className="bg-bg-hard text-fg placeholder:text-fg-4 focus:ring-gruvbox-aqua w-full rounded-lg py-2 pr-10 pl-10 text-sm focus:ring-1 focus:outline-none"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="text-fg-4 hover:text-fg absolute top-1/2 right-3 -translate-y-1/2"
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
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          )}
        </div>
        <button
          onClick={refreshContainers}
          disabled={isLoading}
          className="text-fg-4 hover:text-fg text-sm transition-colors disabled:opacity-50"
        >
          {isLoading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {/* Status Tabs */}
      <div className="border-border-subtle flex border-b">
        {(["running", "exited", "all", "recent"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab
                ? "text-gruvbox-aqua border-gruvbox-aqua"
                : "text-fg-4 hover:text-fg border-transparent"
            }`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}{" "}
            <span className="text-fg-4 text-xs">({counts[tab]})</span>
          </button>
        ))}
      </div>

      {/* Container List */}
      <div className="bg-bg-hard flex-1 overflow-y-auto">
        {isLoading && (
          <div className="text-fg-4 flex items-center justify-center py-12">
            <svg
              className="mr-2 h-5 w-5 animate-spin"
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
            Loading containers...
          </div>
        )}

        {error && (
          <div className="p-4">
            <div className="rounded-md bg-red-900/20 p-4 text-red-400">
              <p className="font-medium">Failed to load containers</p>
              <p className="mt-1 text-sm opacity-80">{error}</p>
            </div>
          </div>
        )}

        {!isLoading && !error && tabContainers.length === 0 && (
          <div className="text-fg-4 py-12 text-center">
            <div className="mb-4 text-4xl opacity-20">
              <ContainerIcon />
            </div>
            <p>No containers found</p>
            {activeTab === "recent" && (
              <p className="mt-2 text-sm opacity-70">
                Attach to containers to see them here
              </p>
            )}
          </div>
        )}

        {!isLoading &&
          !error &&
          tabContainers.length > 0 &&
          filteredContainers.length === 0 && (
            <div className="text-fg-4 py-12 text-center">
              <p>No containers match "{search}"</p>
              <button
                onClick={() => setSearch("")}
                className="mt-2 text-sm underline hover:no-underline"
              >
                Clear search
              </button>
            </div>
          )}

        {!isLoading && !error && filteredContainers.length > 0 && (
          <div className="divide-border-subtle divide-y">
            {filteredContainers.map((container) => (
              <ContainerRow
                key={container.id}
                container={container}
                isAttached={isAttached(container.id)}
                isSelected={selectedId === container.id}
                onClick={handleRowClick}
                onDoubleClick={handleRowDoubleClick}
                searchTerm={search}
              />
            ))}
          </div>
        )}
      </div>

      {/* Footer - Selection info and action button */}
      <div className="border-border-subtle bg-bg-1 border-t px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="text-fg-4 text-sm">
            {selectedId ? (
              <span className="text-fg">
                Selected:{" "}
                <span className="text-gruvbox-yellow font-mono">
                  {containers.find((c) => c.id === selectedId)?.taskId ||
                    selectedId}
                </span>
              </span>
            ) : (
              "Select a container to attach"
            )}
          </div>
          <div className="flex items-center gap-3">
            {removeError && (
              <span className="text-gruvbox-red text-xs">{removeError}</span>
            )}
            {canRemove && (
              <button
                onClick={handleRemove}
                className="border-gruvbox-red text-gruvbox-red hover:bg-gruvbox-red/10 rounded-lg border px-4 py-2 text-sm font-medium transition-colors"
              >
                Remove
              </button>
            )}
            <button
              onClick={handleAttachAll}
              disabled={unattachedIds.length === 0}
              className={`rounded-lg border px-4 py-2 text-sm font-medium transition-colors ${
                unattachedIds.length > 0
                  ? "border-gruvbox-aqua text-gruvbox-aqua hover:bg-gruvbox-aqua/10"
                  : "border-border-subtle text-fg-4 cursor-not-allowed"
              }`}
            >
              Attach all
              {unattachedIds.length > 0 && ` (${unattachedIds.length})`}
            </button>
            <button
              onClick={handleAttach}
              disabled={!selectedId}
              className={`rounded-lg px-6 py-2 text-sm font-medium transition-colors ${
                selectedId
                  ? "bg-gruvbox-aqua text-bg-hard hover:bg-gruvbox-aqua/90"
                  : "bg-bg-2 text-fg-4 cursor-not-allowed"
              }`}
            >
              Attach
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// Container row component
function ContainerRow({
  container,
  isAttached,
  isSelected,
  onClick,
  onDoubleClick,
  searchTerm,
}: {
  container: DockerContainer
  isAttached: boolean
  isSelected: boolean
  onClick: (container: DockerContainer) => void
  onDoubleClick: (container: DockerContainer) => void
  searchTerm: string
}) {
  const statusColors = {
    running: "bg-gruvbox-green",
    exited: "bg-gruvbox-red",
    paused: "bg-gruvbox-yellow",
    created: "bg-gruvbox-blue",
    unknown: "bg-gruvbox-yellow",
  }

  return (
    <button
      onClick={() => onClick(container)}
      onDoubleClick={() => onDoubleClick(container)}
      className={`flex w-full items-center gap-4 px-4 py-3 text-left transition-colors ${
        isSelected
          ? "bg-gruvbox-aqua/20 hover:bg-gruvbox-aqua/25"
          : isAttached
            ? "bg-gruvbox-aqua/10 hover:bg-gruvbox-aqua/15"
            : "hover:bg-bg-1"
      }`}
    >
      {/* Status indicator */}
      <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center">
        {isAttached ? (
          <svg
            className="text-gruvbox-aqua h-5 w-5"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
              clipRule="evenodd"
            />
          </svg>
        ) : (
          <span
            className={`h-2.5 w-2.5 rounded-full ${statusColors[container.status]}`}
          />
        )}
      </span>

      {/* Task ID */}
      <span className="text-gruvbox-yellow w-[160px] flex-shrink-0 truncate font-mono text-sm font-medium">
        <HighlightMatch text={container.taskId} search={searchTerm} />
      </span>

      {/* Model */}
      <span className="text-fg w-[200px] flex-shrink-0 truncate text-sm">
        <HighlightMatch text={container.model} search={searchTerm} />
      </span>

      {/* Agent */}
      <span className="text-fg-4 flex-1 truncate text-sm">
        <HighlightMatch text={container.agent} search={searchTerm} />
      </span>

      {/* Status badge */}
      {isAttached ? (
        <span className="bg-gruvbox-aqua/20 text-gruvbox-aqua flex-shrink-0 rounded px-2 py-1 text-xs font-medium">
          Attached
        </span>
      ) : (
        <span
          className={`flex-shrink-0 rounded px-2 py-1 text-xs font-medium ${
            container.status === "running"
              ? "bg-gruvbox-green/20 text-gruvbox-green"
              : container.status === "exited"
                ? "bg-gruvbox-red/20 text-gruvbox-red"
                : container.status === "paused"
                  ? "bg-gruvbox-yellow/20 text-gruvbox-yellow"
                  : "bg-gruvbox-blue/20 text-gruvbox-blue"
          }`}
        >
          {statusLabel(container)}
        </span>
      )}
    </button>
  )
}

// Highlight matching search text
function HighlightMatch({ text, search }: { text: string; search: string }) {
  if (!search) return <>{text}</>

  const lowerText = text.toLowerCase()
  const lowerSearch = search.toLowerCase()
  const index = lowerText.indexOf(lowerSearch)

  if (index === -1) return <>{text}</>

  return (
    <>
      {text.slice(0, index)}
      <span className="bg-gruvbox-yellow/30 text-gruvbox-yellow">
        {text.slice(index, index + search.length)}
      </span>
      {text.slice(index + search.length)}
    </>
  )
}

function ContainerIcon() {
  return (
    <svg
      className="mx-auto h-8 w-8"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
      />
    </svg>
  )
}
