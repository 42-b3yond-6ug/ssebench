/**
 * LaunchWizard - Multi-step task launcher (Proxmox-style)
 *
 * Provides a step-by-step interface for launching benchmark tasks.
 * Supports selecting multiple tasks that are launched independently.
 * No "Logs" step — the wizard closes after launch and status is tracked
 * in the sidebar via LaunchContext.
 */

import { useState, useEffect, useCallback, useRef } from "react"
import { WizardSteps, type StepId, type StepInfo } from "./WizardSteps"
import { WizardNavigation } from "./WizardNavigation"
import { StepTask } from "./StepTask"
import { StepModel } from "./StepModel"
import { StepAgent } from "./StepAgent"
import { StepMode } from "./StepMode"
import { StepReview, type StepReviewRef } from "./StepReview"
import type { TaskSource, LaunchMode } from "../../types/launch"
import { fetchLaunchConfig, fetchLaunchModels, fetchLaunchAgents } from "../../lib/api"

interface LaunchWizardProps {
  /** Called after launches are fired — closes the wizard */
  onLaunch: () => void
}

const WIZARD_STEPS: StepInfo[] = [
  { id: "task", label: "Task" },
  { id: "model", label: "Model" },
  { id: "agent", label: "Agent" },
  { id: "mode", label: "Mode" },
  { id: "review", label: "Review" },
]

export function LaunchWizard({ onLaunch }: LaunchWizardProps) {
  // Refs
  const stepReviewRef = useRef<StepReviewRef>(null)

  // Wizard state
  const [currentStep, setCurrentStep] = useState(0)
  const [completedSteps, setCompletedSteps] = useState<Set<number>>(new Set())

  // Form state — tasks is now an array
  const [source, setSource] = useState<TaskSource>("remote")
  const [selectedTasks, setSelectedTasks] = useState<string[]>([])
  const [selectedModel, setSelectedModel] = useState("")
  const [selectedAgent, setSelectedAgent] = useState("")
  const [selectedMode, setSelectedMode] = useState<LaunchMode>("sandbox")

  // Data state
  const [models, setModels] = useState<string[]>([])
  const [agents, setAgents] = useState<string[]>([])
  const [hasLocalBenchmarks, setHasLocalBenchmarks] = useState(false)
  const [catalogConfigured, setCatalogConfigured] = useState(false)

  // Loading state
  const [isLoadingConfig, setIsLoadingConfig] = useState(true)
  const [configError, setConfigError] = useState<string | null>(null)

  // Launch state
  const [isLaunching, setIsLaunching] = useState(false)
  const [launchError, setLaunchError] = useState<string | null>(null)

  // Load config on mount
  useEffect(() => {
    const loadConfig = async () => {
      try {
        const [config, modelsData, agentsData] = await Promise.all([
          fetchLaunchConfig(),
          fetchLaunchModels(),
          fetchLaunchAgents(),
        ])

        setHasLocalBenchmarks(config.hasLocalBenchmarks)
        setCatalogConfigured(config.catalogConfigured)
        if (!config.catalogConfigured) setSource("local")
        setModels(modelsData)
        setAgents(agentsData)

        // Set defaults
        if (modelsData.length > 0) setSelectedModel(modelsData[0])
        if (agentsData.length > 0) setSelectedAgent(agentsData[0])
      } catch (err) {
        setConfigError(
          err instanceof Error ? err.message : "Failed to load config"
        )
      } finally {
        setIsLoadingConfig(false)
      }
    }

    loadConfig()
  }, [])

  // Validation for each step
  const isStepValid = useCallback(
    (step: number): boolean => {
      switch (step) {
        case 0:
          return selectedTasks.length > 0
        case 1:
          return !!selectedModel
        case 2:
          return !!selectedAgent
        case 3:
          return !!selectedMode
        case 4:
          return !!(
            selectedTasks.length > 0 &&
            selectedModel &&
            selectedAgent &&
            selectedMode
          )
        default:
          return false
      }
    },
    [selectedTasks, selectedModel, selectedAgent, selectedMode]
  )

  // Navigation handlers
  const handleNext = useCallback(() => {
    if (!isStepValid(currentStep)) return

    // Mark current step as completed
    setCompletedSteps((prev) => new Set(prev).add(currentStep))

    // Move to next step
    if (currentStep < WIZARD_STEPS.length - 1) {
      setCurrentStep(currentStep + 1)
    }
  }, [currentStep, isStepValid])

  const handleBack = useCallback(() => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1)
    }
  }, [currentStep])

  const handleStepClick = useCallback((index: number) => {
    setCurrentStep(index)
  }, [])

  const handleJumpToStep = useCallback((stepId: StepId) => {
    const index = WIZARD_STEPS.findIndex((s) => s.id === stepId)
    if (index !== -1) {
      setCurrentStep(index)
    }
  }, [])

  // Launch handler for wizard navigation button
  const handleLaunchFromNavigation = useCallback(() => {
    if (stepReviewRef.current) {
      stepReviewRef.current.triggerLaunch()
    }
  }, [])

  // Called by StepReview after all POST requests succeed
  const handleLaunched = useCallback(() => {
    setIsLaunching(false)
    // Close wizard — status will be tracked in sidebar
    onLaunch()
  }, [onLaunch])

  // Handle launch error
  const handleLaunchError = useCallback((errorMsg: string) => {
    setLaunchError(errorMsg)
    setIsLaunching(false)
  }, [])

  // Render current step
  const renderCurrentStep = () => {
    const stepId = WIZARD_STEPS[currentStep].id

    switch (stepId) {
      case "task":
        return (
          <StepTask
            source={source}
            selectedTasks={selectedTasks}
            hasLocalBenchmarks={hasLocalBenchmarks}
            catalogConfigured={catalogConfigured}
            onSourceChange={setSource}
            onTasksChange={setSelectedTasks}
          />
        )

      case "model":
        return (
          <StepModel
            models={models}
            selectedModel={selectedModel}
            onModelSelect={setSelectedModel}
          />
        )

      case "agent":
        return (
          <StepAgent
            agents={agents}
            selectedAgent={selectedAgent}
            onAgentSelect={setSelectedAgent}
          />
        )

      case "mode":
        return (
          <StepMode
            selectedMode={selectedMode}
            onModeSelect={setSelectedMode}
          />
        )

      case "review":
        return (
          <StepReview
            ref={stepReviewRef}
            tasks={selectedTasks}
            model={selectedModel}
            agent={selectedAgent}
            mode={selectedMode}
            source={source}
            onEdit={handleJumpToStep}
            onLaunched={handleLaunched}
            onLaunchError={handleLaunchError}
          />
        )

      default:
        return <div>Unknown step</div>
    }
  }

  if (isLoadingConfig) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-fg-4 flex items-center gap-2">
          <svg
            className="h-5 w-5 animate-spin"
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
          Loading configuration...
        </div>
      </div>
    )
  }

  if (configError) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="bg-gruvbox-red/10 text-gruvbox-red rounded-lg p-4">
          <p className="font-medium">Failed to load configuration</p>
          <p className="text-sm">{configError}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      {/* Step indicator tabs */}
      <WizardSteps
        steps={WIZARD_STEPS}
        currentStep={currentStep}
        completedSteps={completedSteps}
        onStepClick={handleStepClick}
        allowFreeNavigation={false}
        disableAllNavigation={isLaunching}
      />

      {/* Launch error banner */}
      {launchError && (
        <div className="bg-gruvbox-red/10 border-gruvbox-red/30 flex items-center gap-2 border-b px-6 py-3">
          <span className="text-gruvbox-red text-sm">{launchError}</span>
          <button
            onClick={() => setLaunchError(null)}
            className="text-gruvbox-red/60 hover:text-gruvbox-red ml-auto text-xs"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Current step content - full height */}
      <div className="flex-1 overflow-y-auto">{renderCurrentStep()}</div>

      {/* Navigation buttons */}
      <WizardNavigation
        currentStep={currentStep}
        totalSteps={WIZARD_STEPS.length}
        isCurrentStepValid={isStepValid(currentStep)}
        isLaunching={isLaunching}
        onBack={handleBack}
        onNext={handleNext}
        onLaunch={
          WIZARD_STEPS[currentStep].id === "review"
            ? handleLaunchFromNavigation
            : undefined
        }
        nextLabel={
          WIZARD_STEPS[currentStep].id === "review" ? undefined : undefined
        }
      />
    </div>
  )
}
