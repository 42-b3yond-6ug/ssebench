/**
 * StepReview - Review and launch step (Final step)
 *
 * Shows summary of all selected tasks and shared configuration.
 * Fires N independent launches (one per task) on submit.
 */

import { useState, useCallback, forwardRef, useImperativeHandle } from "react"
import type { TaskSource, LaunchMode } from "../../types/launch"
import type { StepId } from "./WizardSteps"
import { launchTask } from "../../lib/api"

interface StepReviewProps {
  tasks: string[]
  model: string
  agent: string
  mode: LaunchMode
  source: TaskSource
  onEdit: (step: StepId) => void
  /** Called once all launches have been fired (wizard should close) */
  onLaunched?: () => void
  onLaunchError?: (error: string) => void
}

export interface StepReviewRef {
  triggerLaunch: () => void
  isLaunching: boolean
}

export const StepReview = forwardRef<StepReviewRef, StepReviewProps>(
  function StepReview(
    { tasks, model, agent, mode, source, onEdit, onLaunched, onLaunchError },
    ref
  ) {
    const [isLaunching, setIsLaunching] = useState(false)

    const handleLaunch = useCallback(async () => {
      setIsLaunching(true)

      try {
        // Fire all launches in parallel — each is independent
        const results = await Promise.allSettled(
          tasks.map((task) => launchTask({ task, model, agent, mode, source }))
        )

        // Check if any failed at the API level (not the build itself)
        const failures = results.filter((r) => r.status === "rejected")
        if (failures.length > 0 && failures.length === tasks.length) {
          // All failed
          const firstError =
            failures[0].status === "rejected"
              ? (failures[0].reason as Error).message
              : "Launch failed"
          setIsLaunching(false)
          onLaunchError?.(firstError)
          return
        }

        // At least some succeeded — close the wizard.
        // Individual launch status is tracked via LaunchContext WebSocket.
        onLaunched?.()
      } catch (err) {
        setIsLaunching(false)
        onLaunchError?.(err instanceof Error ? err.message : "Launch failed")
      }
    }, [tasks, model, agent, mode, source, onLaunched, onLaunchError])

    // Expose launch function to parent via ref
    useImperativeHandle(
      ref,
      () => ({
        triggerLaunch: handleLaunch,
        isLaunching,
      }),
      [handleLaunch, isLaunching]
    )

    const taskCount = tasks.length
    const launchLabel =
      taskCount === 1 ? "Launch Task" : `Launch ${taskCount} Tasks`

    return (
      <div className="flex h-full flex-col p-6">
        {/* Step header */}
        <div className="mb-6">
          <h2 className="text-fg mb-2 text-xl font-semibold">
            Review Your Configuration
          </h2>
          <p className="text-fg-4 text-sm">
            Verify your selections before launching{" "}
            {taskCount === 1 ? "the benchmark task" : `${taskCount} tasks`}
          </p>
        </div>

        {/* Configuration summary */}
        <div className="border-border mb-6 rounded-lg border">
          <div className="divide-border-subtle divide-y">
            {/* Tasks — show list */}
            <div className="flex items-start justify-between px-4 py-3">
              <div className="flex items-start gap-3">
                <span className="text-fg-4 w-20 flex-shrink-0 pt-0.5 text-sm">
                  Tasks:
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {tasks.map((task) => (
                    <span
                      key={task}
                      className="bg-bg-hard text-gruvbox-yellow rounded px-2 py-0.5 font-mono text-xs"
                    >
                      {task}
                    </span>
                  ))}
                </div>
              </div>
              <button
                onClick={() => onEdit("task")}
                className="text-gruvbox-aqua hover:text-gruvbox-aqua/80 flex-shrink-0 text-xs font-medium transition-colors"
              >
                Edit
              </button>
            </div>

            <SummaryRow
              label="Model"
              value={model}
              onEdit={() => onEdit("model")}
            />
            <SummaryRow
              label="Agent"
              value={agent}
              onEdit={() => onEdit("agent")}
            />
            <SummaryRow
              label="Mode"
              value={mode}
              onEdit={() => onEdit("mode")}
            />
          </div>
        </div>

        {/* Command preview */}
        <div className="bg-bg-hard border-border rounded-lg border p-4">
          <p className="text-fg-4 mb-2 text-xs font-medium">
            {taskCount === 1 ? "Command Preview:" : `Commands (${taskCount}):`}
          </p>
          {taskCount <= 3 ? (
            tasks.map((task) => (
              <code
                key={task}
                className="text-fg-3 block font-mono text-xs leading-relaxed"
              >
                ssebench run --task {task} --model {model} --agent {agent}{" "}
                --mode {mode}
              </code>
            ))
          ) : (
            <>
              <code className="text-fg-3 block font-mono text-xs leading-relaxed">
                ssebench run --task {tasks[0]} --model {model} --agent {agent}{" "}
                --mode {mode}
              </code>
              <code className="text-fg-4 block font-mono text-xs leading-relaxed">
                ... and {taskCount - 1} more
              </code>
            </>
          )}
        </div>

        {/* Spacer to push content up */}
        <div className="flex-1" />

        {/* Info text */}
        <p className="text-fg-4 text-center text-sm">
          Click{" "}
          <span className="text-gruvbox-aqua font-medium">{launchLabel}</span>{" "}
          to begin
        </p>
      </div>
    )
  }
)

interface SummaryRowProps {
  label: string
  value: string
  onEdit: () => void
}

function SummaryRow({ label, value, onEdit }: SummaryRowProps) {
  return (
    <div className="flex items-center justify-between px-4 py-3">
      <div className="flex items-center gap-3">
        <span className="text-fg-4 w-20 text-sm">{label}:</span>
        <span className="text-fg font-mono text-sm">{value}</span>
      </div>
      <button
        onClick={onEdit}
        className="text-gruvbox-aqua hover:text-gruvbox-aqua/80 text-xs font-medium transition-colors"
      >
        Edit
      </button>
    </div>
  )
}
