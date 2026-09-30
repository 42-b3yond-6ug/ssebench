/**
 * WizardSteps - Proxmox-style tab indicator for multi-step wizard
 */

export type StepId = "task" | "agent" | "model" | "mode" | "options" | "review"

export interface StepInfo {
  id: StepId
  label: string
}

interface WizardStepsProps {
  steps: StepInfo[]
  currentStep: number
  completedSteps: Set<number>
  onStepClick?: (index: number) => void
  allowFreeNavigation?: boolean
  disableAllNavigation?: boolean
}

export function WizardSteps({
  steps,
  currentStep,
  completedSteps,
  onStepClick,
  allowFreeNavigation = false,
  disableAllNavigation = false,
}: WizardStepsProps) {
  const handleStepClick = (index: number) => {
    if (!onStepClick) return

    // If all navigation is disabled (e.g., during launch), prevent any clicks
    if (disableAllNavigation) return

    // If free navigation is disabled, only allow clicking on completed steps or current step
    if (!allowFreeNavigation && index > currentStep) return

    onStepClick(index)
  }

  return (
    <div className="border-border flex border-b">
      {steps.map((step, index) => {
        const isCompleted = completedSteps.has(index)
        const isCurrent = index === currentStep
        const isClickable =
          !disableAllNavigation &&
          (allowFreeNavigation || index <= currentStep || isCompleted)

        return (
          <button
            key={step.id}
            onClick={() => handleStepClick(index)}
            disabled={!isClickable}
            className={`flex flex-1 items-center justify-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
              isCurrent
                ? "text-gruvbox-orange border-gruvbox-orange"
                : isCompleted
                  ? "text-gruvbox-green hover:border-gruvbox-green/50 border-transparent"
                  : "text-fg-4 border-transparent"
            } ${isClickable ? "cursor-pointer" : "cursor-not-allowed"}`}
          >
            {/* Step indicator */}
            <span className="flex items-center justify-center">
              {isCompleted ? (
                // Checkmark for completed steps
                <svg
                  className="text-gruvbox-green h-5 w-5"
                  fill="currentColor"
                  viewBox="0 0 20 20"
                >
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                    clipRule="evenodd"
                  />
                </svg>
              ) : isCurrent ? (
                // Orange dot for current step
                <svg
                  className="h-5 w-5"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <circle cx="10" cy="10" r="4" />
                </svg>
              ) : (
                // Gray dot for incomplete steps
                <svg
                  className="h-5 w-5"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <circle cx="10" cy="10" r="3" opacity="0.3" />
                </svg>
              )}
            </span>

            {/* Step label */}
            <span>{step.label}</span>
          </button>
        )
      })}
    </div>
  )
}
