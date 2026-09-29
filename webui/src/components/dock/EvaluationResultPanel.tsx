/**
 * Evaluation Result Panel - Shows patch evaluation results
 *
 * Extracted from the old RightPanel to be a standalone panel in the dock system.
 * Displays build success, PoV test pass rate, functional test, and intent test results.
 */

import { useState } from "react"
import { useContainers } from "../../context/ContainerContext"
import { useSDKDataContext } from "../../context/SDKDataContext"
import type { EvaluationResultResponse } from "../../types/container"

// =============================================================================
// Main Panel Component
// =============================================================================

export function EvaluationResultPanel() {
  const { evaluationResult, resultAvailable } = useSDKDataContext()
  const { activeContainer } = useContainers()

  if (!resultAvailable || !evaluationResult) {
    return (
      <div className="text-fg-4 flex h-full flex-col items-center justify-center px-4">
        <svg
          className="mb-4 h-12 w-12 opacity-20"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"
          />
        </svg>
        <h3 className="text-fg-3 mb-2 text-sm font-medium">
          No evaluation yet
        </h3>
        <p className="max-w-xs text-center text-xs">
          Evaluation results will appear here after the agent completes its task
          and the patch is tested.
        </p>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto p-4">
      <ResultCard
        result={evaluationResult}
        referenceRun={activeContainer?.referenceRun ?? false}
      />
    </div>
  )
}

// =============================================================================
// Result Card
// =============================================================================

function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)

  if (hours > 0) {
    return `${hours}h ${minutes % 60}m`
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`
  }
  return `${seconds}s`
}

function MetricBadge({
  label,
  status,
  icon,
}: {
  label: string
  status: boolean | null | undefined
  icon: React.ReactNode
}) {
  const color =
    status === true
      ? "text-gruvbox-green"
      : status === false
        ? "text-gruvbox-red"
        : "text-fg-4"

  const statusText =
    status === true ? "Pass" : status === false ? "Fail" : "N/A"

  return (
    <div className="flex flex-col items-center gap-1">
      <div className={color}>{icon}</div>
      <div className="text-fg-4 text-[10px] uppercase">{label}</div>
      <div className={`text-xs font-medium ${color}`}>{statusText}</div>
    </div>
  )
}

function ResultCard({
  result,
  referenceRun,
}: {
  result: EvaluationResultResponse
  referenceRun: boolean
}) {
  const [showErrorLog, setShowErrorLog] = useState(false)

  // Waiting state - shown while polling for result
  if (!result.available) {
    return (
      <div className="bg-bg-1 border-border-subtle rounded-lg border p-3">
        <div className="text-fg-4 flex items-center gap-2 text-sm">
          <svg
            className="text-gruvbox-purple h-5 w-5 animate-pulse"
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
          <span>Evaluating patch...</span>
        </div>
        <div className="text-fg-4/60 mt-1 text-xs">
          Running build and security tests
        </div>
      </div>
    )
  }

  const { patch_result, runtime_result } = result

  const buildSuccess = patch_result?.build_success
  const povPassed = patch_result?.pov_passed ?? 0
  const povTotal = patch_result?.pov_total ?? 0
  const funcSuccess = patch_result?.func_test_success
  const intentSuccess = patch_result?.intent_test_success
  const hasError = patch_result?.error_msg

  const isPovSuccess = povTotal > 0 && povPassed === povTotal
  const isPovPartial = povTotal > 0 && povPassed > 0 && povPassed < povTotal
  const isBuildFail = buildSuccess === false
  const isIntentFail = intentSuccess === false

  const borderColor = isBuildFail
    ? "border-gruvbox-red"
    : isIntentFail
      ? "border-gruvbox-yellow"
      : isPovSuccess
        ? "border-gruvbox-green"
        : isPovPartial
          ? "border-gruvbox-yellow"
          : "border-gruvbox-gray"

  return (
    <div className={`bg-bg-1 rounded-lg border-2 p-3 ${borderColor}`}>
      {/* Header */}
      <div className="mb-2 flex items-center gap-2">
        <svg
          className="text-gruvbox-purple h-4 w-4"
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
        <span className="text-fg text-xs font-medium">Evaluation Result</span>
      </div>

      {referenceRun && (
        <div className="bg-gruvbox-blue/10 text-gruvbox-blue mb-2 rounded p-2 text-[10px]">
          <div className="mb-1 font-medium">Reference run</div>
          <div className="opacity-90">
            The task&apos;s known fix was applied, so this grade checks the
            task, not a model.
          </div>
        </div>
      )}

      {/* Metrics Grid */}
      {patch_result && (
        <div className="border-border-subtle grid grid-cols-4 gap-2 border-t pt-2">
          <MetricBadge
            label="Build"
            status={buildSuccess}
            icon={
              <svg
                className="h-3.5 w-3.5"
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
            }
          />
          <MetricBadge
            label="Func"
            status={funcSuccess}
            icon={
              <svg
                className="h-3.5 w-3.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"
                />
              </svg>
            }
          />
          <div className="flex flex-col items-center gap-1">
            <div
              className={
                povTotal > 0
                  ? isPovSuccess
                    ? "text-gruvbox-green"
                    : isPovPartial
                      ? "text-gruvbox-yellow"
                      : "text-gruvbox-red"
                  : "text-fg-4"
              }
            >
              <svg
                className="h-3.5 w-3.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                />
              </svg>
            </div>
            <div className="text-fg-4 text-[10px] uppercase">Security</div>
            <div
              className={`text-xs font-medium ${povTotal > 0 ? (isPovSuccess ? "text-gruvbox-green" : isPovPartial ? "text-gruvbox-yellow" : "text-gruvbox-red") : "text-fg-4"}`}
            >
              {povTotal > 0 ? `${povPassed}/${povTotal}` : "N/A"}
            </div>
          </div>
          <MetricBadge
            label="Intent"
            status={intentSuccess}
            icon={
              <svg
                className="h-3.5 w-3.5"
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
            }
          />
        </div>
      )}

      {/* Runtime Stats */}
      {runtime_result && (
        <div className="border-border-subtle mt-2 flex flex-wrap items-center gap-2 border-t pt-2 text-[10px]">
          <div className="text-fg-4">
            <span className="text-fg-3 font-mono">
              {formatDuration(runtime_result.agent_duration * 1000)}
            </span>
          </div>
          {runtime_result.agent_timeout && (
            <div className="bg-gruvbox-orange/20 text-gruvbox-orange rounded px-1 py-0.5 font-medium">
              TIMEOUT
            </div>
          )}
        </div>
      )}

      {/* Error Section */}
      {hasError && (
        <div className="border-border-subtle mt-2 border-t pt-2">
          <div className="bg-gruvbox-red/10 text-gruvbox-red rounded p-2 text-[10px]">
            <div className="mb-1 font-medium">Error</div>
            <div className="opacity-90">{patch_result.error_msg}</div>
          </div>
          {patch_result.error_log && (
            <>
              <button
                onClick={() => setShowErrorLog(!showErrorLog)}
                className="text-fg-4 hover:text-fg-3 mt-1 flex items-center gap-1 text-[10px] transition-colors"
              >
                <svg
                  className={`h-2.5 w-2.5 transition-transform ${showErrorLog ? "rotate-90" : ""}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 5l7 7-7 7"
                  />
                </svg>
                {showErrorLog ? "Hide" : "Show"} log
              </button>
              {showErrorLog && (
                <pre className="bg-bg-2 text-fg-4 mt-1 max-h-32 overflow-auto rounded p-2 font-mono text-[9px] leading-relaxed">
                  {patch_result.error_log}
                </pre>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
