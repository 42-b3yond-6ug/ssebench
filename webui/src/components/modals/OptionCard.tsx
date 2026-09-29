/**
 * OptionCard - Reusable card component for selections
 *
 * Inspired by ThemeOption in SettingsPanel - same beautiful design!
 */

import type { ReactNode } from "react"

interface OptionCardProps {
  /** Display name */
  name: string

  /** Description text */
  description?: string

  /** Whether this option is selected */
  isSelected: boolean

  /** Callback when card is clicked */
  onSelect: () => void

  /** Optional icon to display */
  icon?: ReactNode

  /** Optional badge text */
  badge?: ReactNode

  /** Optional visual preview content */
  visualContent?: ReactNode

  /** Disabled state */
  disabled?: boolean

  /** Size variant */
  size?: "normal" | "large"
}

export function OptionCard({
  name,
  description,
  isSelected,
  onSelect,
  icon,
  badge,
  visualContent,
  disabled = false,
  size = "normal",
}: OptionCardProps) {
  const sizeClasses = size === "large" ? "p-6" : "p-4"

  return (
    <button
      onClick={onSelect}
      disabled={disabled}
      className={`border-border hover:border-gruvbox-orange/50 group relative flex flex-col gap-3 rounded-lg border-2 text-left transition-all ${sizeClasses} ${
        isSelected
          ? "border-gruvbox-orange bg-gruvbox-orange/5"
          : "bg-bg-1 hover:bg-bg-2"
      } ${disabled ? "cursor-not-allowed opacity-50" : ""}`}
    >
      {/* Selected indicator */}
      {isSelected && (
        <div className="absolute top-2 right-2">
          <svg
            className="text-gruvbox-orange h-5 w-5"
            fill="currentColor"
            viewBox="0 0 20 20"
          >
            <path
              fillRule="evenodd"
              d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
              clipRule="evenodd"
            />
          </svg>
        </div>
      )}

      {/* Badge (top-left) */}
      {badge && <div className="absolute top-2 left-2">{badge}</div>}

      {/* Icon (if no visual content) */}
      {icon && !visualContent && (
        <div className="text-fg-3 flex items-center justify-center text-3xl">
          {icon}
        </div>
      )}

      {/* Name and description */}
      <div className={badge ? "ml-8" : ""}>
        <h4
          className={`font-medium ${
            isSelected ? "text-gruvbox-orange" : "text-fg"
          } ${size === "large" ? "text-base" : "text-sm"}`}
        >
          {name}
        </h4>
        {description && (
          <p
            className={`text-fg-4 ${size === "large" ? "text-sm" : "text-xs"} mt-1`}
          >
            {description}
          </p>
        )}
      </div>

      {/* Visual content (like color palette or diagrams) */}
      {visualContent && <div className="mt-2">{visualContent}</div>}
    </button>
  )
}
