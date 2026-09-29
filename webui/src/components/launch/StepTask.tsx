/**
 * StepTask - Task selection step (Step 1)
 *
 * Allows users to choose one or more benchmark tasks from the task catalog
 * (remote) or from local task directories.
 * Supports multi-select with checkboxes for batch launching.
 */

import { useState, useEffect, useMemo, useCallback } from "react"
import { fetchLaunchTasks } from "../../lib/api"
import type { Task, TaskSource } from "../../types/launch"

interface StepTaskProps {
  source: TaskSource
  selectedTasks: string[]
  hasLocalBenchmarks: boolean
  catalogConfigured: boolean
  onSourceChange: (source: TaskSource) => void
  onTasksChange: (taskIds: string[]) => void
}

export function StepTask({
  source,
  selectedTasks,
  hasLocalBenchmarks,
  catalogConfigured,
  onSourceChange,
  onTasksChange,
}: StepTaskProps) {
  const [remoteTasks, setRemoteTasks] = useState<Task[]>([])
  const [remoteError, setRemoteError] = useState<string | null>(null)
  const [localTasks, setLocalTasks] = useState<Task[]>([])
  const [taskSearch, setTaskSearch] = useState("")
  const [isLoading, setIsLoading] = useState(true)

  // Load tasks
  useEffect(() => {
    const loadTasks = async () => {
      setIsLoading(true)
      try {
        const [remote, local] = await Promise.all([
          catalogConfigured
            ? fetchLaunchTasks("remote").catch((err: unknown) => {
                setRemoteError(
                  err instanceof Error ? err.message : "Failed to fetch tasks"
                )
                return []
              })
            : [],
          fetchLaunchTasks("local").catch(() => []),
        ])
        setRemoteTasks(remote)
        setLocalTasks(local)
      } finally {
        setIsLoading(false)
      }
    }

    loadTasks()
  }, [catalogConfigured])

  // Clear selection when source changes
  useEffect(() => {
    onTasksChange([])
    setTaskSearch("")
  }, [source, onTasksChange])

  // Derive current tasks from source
  const tasks = source === "remote" ? remoteTasks : localTasks
  const remoteTaskCount = remoteTasks.length
  const localTaskCount = localTasks.length

  // Filter tasks by search
  const filteredTasks = useMemo(() => {
    if (!taskSearch) return tasks
    const searchLower = taskSearch.toLowerCase()
    return tasks.filter(
      (t) =>
        t.id.toLowerCase().includes(searchLower) ||
        t.language?.toLowerCase().includes(searchLower) ||
        t.project?.toLowerCase().includes(searchLower)
    )
  }, [tasks, taskSearch])

  // Toggle a single task
  const toggleTask = useCallback(
    (taskId: string) => {
      if (selectedTasks.includes(taskId)) {
        onTasksChange(selectedTasks.filter((id) => id !== taskId))
      } else {
        onTasksChange([...selectedTasks, taskId])
      }
    },
    [selectedTasks, onTasksChange]
  )

  // Select/deselect all visible tasks
  const toggleAll = useCallback(() => {
    const visibleIds = filteredTasks.slice(0, 100).map((t) => t.id)
    const allSelected = visibleIds.every((id) => selectedTasks.includes(id))

    if (allSelected) {
      // Deselect all visible
      onTasksChange(selectedTasks.filter((id) => !visibleIds.includes(id)))
    } else {
      // Select all visible (merge with existing)
      const merged = new Set([...selectedTasks, ...visibleIds])
      onTasksChange(Array.from(merged))
    }
  }, [filteredTasks, selectedTasks, onTasksChange])

  const visibleIds = filteredTasks.slice(0, 100).map((t) => t.id)
  const allVisibleSelected =
    visibleIds.length > 0 &&
    visibleIds.every((id) => selectedTasks.includes(id))

  return (
    <div className="flex h-full flex-col p-6">
      {/* Step header */}
      <div className="mb-6">
        <h2 className="text-fg mb-2 text-xl font-semibold">
          Select Benchmark Tasks
        </h2>
        <p className="text-fg-4 text-sm">
          Choose one or more tasks to launch.{" "}
          {selectedTasks.length > 0 && (
            <span className="text-gruvbox-aqua font-medium">
              {selectedTasks.length} selected
            </span>
          )}
        </p>
      </div>

      {/* Source tabs */}
      <div className="border-border-subtle mb-4 flex rounded-lg border">
        <button
          onClick={() => onSourceChange("remote")}
          disabled={!catalogConfigured}
          className={`flex-1 rounded-l-lg px-4 py-2 text-sm font-medium transition-colors ${
            !catalogConfigured
              ? "text-fg-4/50 cursor-not-allowed"
              : source === "remote"
                ? "bg-gruvbox-aqua/10 text-gruvbox-aqua"
                : "text-fg-4 hover:bg-bg-2 hover:text-fg"
          }`}
          title={
            !catalogConfigured
              ? "Task catalog not configured (SSEBENCH_CATALOG_URL)"
              : undefined
          }
        >
          Catalog{" "}
          <span className="text-fg-4 text-xs">
            ({!catalogConfigured ? "off" : isLoading ? "..." : remoteTaskCount})
          </span>
        </button>
        <button
          onClick={() => onSourceChange("local")}
          disabled={!hasLocalBenchmarks}
          className={`flex-1 rounded-r-lg px-4 py-2 text-sm font-medium transition-colors ${
            !hasLocalBenchmarks
              ? "text-fg-4/50 cursor-not-allowed"
              : source === "local"
                ? "bg-gruvbox-aqua/10 text-gruvbox-aqua"
                : "text-fg-4 hover:bg-bg-2 hover:text-fg"
          }`}
          title={!hasLocalBenchmarks ? "No local tasks found" : undefined}
        >
          Local{" "}
          <span className="text-fg-4 text-xs">
            ({isLoading ? "..." : localTaskCount})
          </span>
        </button>
      </div>

      {/* Search bar + select all */}
      <div className="mb-4 flex items-center gap-3">
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
            value={taskSearch}
            onChange={(e) => setTaskSearch(e.target.value)}
            placeholder="Search tasks by ID, language, or project..."
            className="bg-bg-hard text-fg placeholder:text-fg-4 focus:ring-gruvbox-aqua w-full rounded-lg py-2 pr-4 pl-10 text-sm focus:ring-2 focus:outline-none"
          />
        </div>

        {/* Select all toggle */}
        {filteredTasks.length > 0 && (
          <button
            onClick={toggleAll}
            className="text-fg-4 hover:text-gruvbox-aqua whitespace-nowrap text-xs font-medium transition-colors"
          >
            {allVisibleSelected ? "Deselect all" : "Select all"}
          </button>
        )}
      </div>

      {/* Task list - full remaining height */}
      <div className="bg-bg-hard border-border flex-1 overflow-y-auto rounded-lg border">
        {isLoading ? (
          <div className="text-fg-4 flex h-full items-center justify-center">
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
            Loading tasks...
          </div>
        ) : source === "remote" && !catalogConfigured ? (
          <div className="text-fg-4 flex h-full flex-col items-center justify-center gap-1 px-6 text-center text-sm">
            <p className="text-fg font-medium">Task catalog not configured</p>
            <p>
              Set <code className="font-mono">SSEBENCH_CATALOG_URL</code> for
              the webui server to list catalog tasks, or use local tasks.
            </p>
          </div>
        ) : source === "remote" && remoteError ? (
          <div className="text-gruvbox-red flex h-full items-center justify-center px-6 text-center text-sm">
            {remoteError}
          </div>
        ) : filteredTasks.length === 0 ? (
          <div className="text-fg-4 flex h-full items-center justify-center text-sm">
            {taskSearch
              ? "No tasks match your search"
              : source === "local"
                ? "No local tasks found"
                : "No tasks available"}
          </div>
        ) : (
          <div className="divide-border-subtle divide-y">
            {filteredTasks.slice(0, 100).map((task) => {
              const isSelected = selectedTasks.includes(task.id)
              return (
                <button
                  key={task.id}
                  onClick={() => toggleTask(task.id)}
                  className={`flex w-full items-center gap-3 px-4 py-3 text-left text-sm transition-colors ${
                    isSelected
                      ? "bg-gruvbox-aqua/10 text-gruvbox-aqua"
                      : "hover:bg-bg-2 text-fg"
                  }`}
                >
                  {/* Checkbox */}
                  <span
                    className={`flex h-4 w-4 flex-shrink-0 items-center justify-center rounded border transition-colors ${
                      isSelected
                        ? "border-gruvbox-aqua bg-gruvbox-aqua"
                        : "border-fg-4/40"
                    }`}
                  >
                    {isSelected && (
                      <svg
                        className="text-bg-hard h-3 w-3"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth={3}
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                    )}
                  </span>

                  <span className="text-gruvbox-yellow font-mono font-medium">
                    {task.id}
                  </span>
                  {task.language && (
                    <span className="bg-bg-1 text-fg-4 rounded px-2 py-0.5 text-xs">
                      {task.language}
                    </span>
                  )}
                </button>
              )
            })}
            {filteredTasks.length > 100 && (
              <div className="text-fg-4 py-3 text-center text-xs">
                Showing first 100 of {filteredTasks.length} tasks
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
