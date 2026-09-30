/**
 * Turns the errors that OpenCode reports for a message or a session into text
 * for the assistant tab.
 */

import type { OpenCodeErrorInfo } from "../types/opencode"

/** Errors that mean the user stopped the answer, not that it failed */
const IGNORED = new Set(["MessageAbortedError"])

const UNREACHABLE =
  /unable to connect|econnrefused|enotfound|eai_again|fetch failed|timed? ?out|network|socket/i

/** Whether the error is one to show */
export function isReportable(error: OpenCodeErrorInfo | undefined): boolean {
  return !!error && !IGNORED.has(error.name)
}

/**
 * One line for the error banner, with a hint when the provider looks
 * unreachable: a container on the restricted network reaches only the LiteLLM
 * proxy, not the internet.
 */
export function describeOpenCodeError(error: OpenCodeErrorInfo): string {
  const detail = error.data
  const status = detail?.statusCode ? ` (HTTP ${detail.statusCode})` : ""
  const message = `${detail?.message || error.name}${status}`
  const unreachable = UNREACHABLE.test(
    `${detail?.message ?? ""} ${detail?.responseBody ?? ""}`
  )
  return unreachable
    ? `${message}. The container may have no route to the model provider: a run on the restricted network reaches only the LiteLLM proxy. Use a run with a model, whose assistant goes through the proxy, or start the run with --egress open.`
    : message
}
