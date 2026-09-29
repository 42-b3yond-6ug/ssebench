/**
 * ViewContainer - Reusable wrapper for middle panel views
 *
 * Provides consistent flex layout that works correctly in the middle panel.
 * Prevents common layout bugs like uncontrolled expansion or misalignment.
 *
 * Usage:
 *   <ViewContainer>
 *     <YourContent />
 *   </ViewContainer>
 *
 *   <ViewContainer centered>
 *     <PromptBox />
 *   </ViewContainer>
 */

import type { ReactNode } from "react"

interface ViewContainerProps {
  children: ReactNode
  /** Center content both horizontally and vertically */
  centered?: boolean
  /** Additional CSS classes */
  className?: string
}

export function ViewContainer({
  children,
  centered = false,
  className = "",
}: ViewContainerProps) {
  const baseClasses = "flex min-h-0 min-w-0 flex-1 flex-col"
  const centeredClasses = centered ? "items-center justify-center" : ""
  const combinedClasses =
    `${baseClasses} ${centeredClasses} ${className}`.trim()

  return <div className={combinedClasses}>{children}</div>
}
