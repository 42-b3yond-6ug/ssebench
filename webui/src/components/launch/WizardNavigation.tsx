/**
 * WizardNavigation - Back/Next buttons for wizard navigation
 */

interface WizardNavigationProps {
  currentStep: number
  totalSteps: number
  isCurrentStepValid: boolean
  isLaunching?: boolean
  onBack: () => void
  onNext: () => void
  onLaunch?: () => void
  backLabel?: string
  nextLabel?: string
}

export function WizardNavigation({
  currentStep,
  totalSteps,
  isCurrentStepValid,
  isLaunching = false,
  onBack,
  onNext,
  onLaunch,
  backLabel,
  nextLabel,
}: WizardNavigationProps) {
  const isFirstStep = currentStep === 0
  const isLastStep = currentStep === totalSteps - 1

  return (
    <div className="border-border-subtle bg-bg-1 flex items-center justify-between border-t px-6 py-4">
      {/* Back button */}
      <button
        onClick={onBack}
        disabled={isFirstStep}
        className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
          isFirstStep
            ? "text-fg-4 cursor-not-allowed opacity-50"
            : "text-fg hover:bg-bg-2"
        }`}
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
            d="M15 19l-7-7 7-7"
          />
        </svg>
        {backLabel || "Back"}
      </button>

      {/* Next/Launch button */}
      {isLastStep && onLaunch ? (
        <button
          onClick={onLaunch}
          disabled={!isCurrentStepValid || isLaunching}
          className={`flex items-center gap-2 rounded-lg px-6 py-2 text-sm font-medium transition-colors ${
            isCurrentStepValid && !isLaunching
              ? "bg-gruvbox-aqua text-bg-hard hover:bg-gruvbox-aqua/90"
              : "bg-bg-2 text-fg-4 cursor-not-allowed"
          }`}
        >
          {isLaunching ? (
            <>
              <svg
                className="h-4 w-4 animate-spin"
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
              Launching...
            </>
          ) : (
            <>🚀 Launch Task</>
          )}
        </button>
      ) : (
        <button
          onClick={onNext}
          disabled={!isCurrentStepValid}
          className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
            isCurrentStepValid
              ? "bg-gruvbox-aqua text-bg-hard hover:bg-gruvbox-aqua/90"
              : "bg-bg-2 text-fg-4 cursor-not-allowed"
          }`}
        >
          {nextLabel || "Next"}
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
              d="M9 5l7 7-7 7"
            />
          </svg>
        </button>
      )}
    </div>
  )
}
