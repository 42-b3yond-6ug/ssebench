/**
 * StepModel - Model selection step (Step 2)
 *
 * Vendor-grouped model cards in a beautiful 3-column layout.
 * Anthropic expanded by default, others collapsed.
 */

import { useState, useMemo } from "react"
import { OptionCard } from "../modals/OptionCard"
import { groupModelsByVendor, cleanModelName } from "../../lib/modelUtils"
import { VendorIcon } from "../icons/VendorIcon"

interface StepModelProps {
  models: string[]
  selectedModel: string
  onModelSelect: (model: string) => void
  /** The reference agent makes no model calls, so it needs no model */
  noModelNeeded?: boolean
  /** By model, the provider keys `.env` lacks; a model missing here is unchecked */
  missingKeys?: Record<string, string[]>
}

export function StepModel({
  models,
  selectedModel,
  onModelSelect,
  noModelNeeded = false,
  missingKeys = {},
}: StepModelProps) {
  // Group models by vendor
  const modelGroups = useMemo(() => groupModelsByVendor(models), [models])

  // Track expanded vendors (Anthropic expanded by default)
  const [expandedVendors, setExpandedVendors] = useState<Set<string>>(
    new Set(["anthropic"])
  )

  const toggleVendor = (vendor: string) => {
    setExpandedVendors((prev) => {
      const next = new Set(prev)
      if (next.has(vendor)) {
        next.delete(vendor)
      } else {
        next.add(vendor)
      }
      return next
    })
  }

  const getVendorIcon = (vendor: string) => {
    return (
      <VendorIcon
        vendor={vendor as "anthropic" | "openai" | "google"}
        size="md"
      />
    )
  }

  if (noModelNeeded) {
    return (
      <div className="h-full overflow-y-auto p-6">
        <h2 className="text-fg mb-2 text-xl font-semibold">No Model Needed</h2>
        <p className="text-fg-4 text-sm">
          The reference agent applies the task&apos;s known fix and makes no
          model calls, so the run has no model and needs no provider key.
        </p>
      </div>
    )
  }

  const missingForSelected = missingKeys[selectedModel] ?? []

  return (
    <div className="h-full overflow-y-auto p-6">
      {/* Step header */}
      <div className="mb-6">
        <h2 className="text-fg mb-2 text-xl font-semibold">
          Choose a Language Model
        </h2>
        <p className="text-fg-4 text-sm">
          Select the AI model to use for the benchmark task
        </p>
      </div>

      {missingForSelected.length > 0 && (
        <div
          role="alert"
          className="bg-gruvbox-yellow/10 border-gruvbox-yellow text-fg-2 mb-4 rounded-lg border p-3 text-sm"
        >
          <span className="text-gruvbox-yellow font-medium">
            {selectedModel} needs {missingForSelected.join(", ")}
          </span>{" "}
          in <code className="font-mono">.env</code>, which has no value for it.
          The run fails when the agent first calls the model. Add the key and
          restart the proxy with{" "}
          <code className="font-mono">ssebench proxy up</code>.
        </div>
      )}

      {/* Vendor groups */}
      <div className="space-y-4">
        {modelGroups.map((group) => {
          const isExpanded = expandedVendors.has(group.vendor)

          return (
            <div key={group.vendor} className="border-border rounded-lg border">
              {/* Vendor header */}
              <button
                onClick={() => toggleVendor(group.vendor)}
                className="hover:bg-bg-2 flex w-full items-center justify-between px-4 py-3 transition-colors"
              >
                <div className="flex items-center gap-3">
                  {getVendorIcon(group.vendor)}
                  <span className="text-fg font-medium">
                    {group.vendorDisplayName}
                  </span>
                  <span className="text-fg-4 text-sm">
                    ({group.models.length} models)
                  </span>
                </div>
                <svg
                  className={`text-fg-4 h-5 w-5 transition-transform ${
                    isExpanded ? "rotate-180" : ""
                  }`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 9l-7 7-7-7"
                  />
                </svg>
              </button>

              {/* Model cards grid */}
              {isExpanded && (
                <div className="border-border grid grid-cols-1 gap-3 border-t p-4 sm:grid-cols-2 lg:grid-cols-3">
                  {group.models.map((model) => (
                    <OptionCard
                      key={model}
                      name={cleanModelName(model)}
                      description={
                        missingKeys[model]?.length
                          ? `Key missing: ${missingKeys[model].join(", ")}`
                          : undefined
                      }
                      isSelected={selectedModel === model}
                      onSelect={() => onModelSelect(model)}
                      size="normal"
                    />
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
