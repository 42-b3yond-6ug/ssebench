/**
 * Defaults of the launch options: those of `ssebench run`, so that an option
 * the user leaves alone is not passed on.
 */

import type { Egress } from "../types/launch"

export const DEFAULT_DIFFICULTY = 2
export const DEFAULT_TIMEOUT_MINUTES = 60
/** The most the server accepts: 7 days */
export const MAX_TIMEOUT_MINUTES = 7 * 24 * 60
export const DEFAULT_EGRESS: Egress = "restricted"

/** Whether a timeout in minutes is one the server accepts */
export function isValidTimeout(minutes: number): boolean {
  return (
    Number.isInteger(minutes) && minutes >= 1 && minutes <= MAX_TIMEOUT_MINUTES
  )
}
