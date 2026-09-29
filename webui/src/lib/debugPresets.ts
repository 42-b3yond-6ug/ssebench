/**
 * Debug Preset Prompts for OpenCode
 *
 * Provides pre-configured prompts for common debugging scenarios.
 * Templates are functions that generate prompts based on context.
 */

export interface PresetContext {
  /** Source code directory */
  sourceDir: string
  /** Whether ground truth patch is available */
  groundTruthAvailable: boolean
  /** Ground truth patch content (if available) */
  groundTruthContent?: string
  /** Project/task ID */
  projectId: string
  /** Programming language */
  language: string
}

export interface DebugPreset {
  /** Unique identifier */
  id: string
  /** Display name */
  label: string
  /** Emoji icon */
  icon: string
  /** Short description */
  description: string
  /** Function that generates the prompt message */
  template: (context: PresetContext) => string
  /** Whether this preset requires ground truth */
  requiresGroundTruth?: boolean
}

export const debugPresets: DebugPreset[] = [
  {
    id: "compare-fixes",
    label: "Compare Agent Fix with Ground Truth",
    icon: "📊",
    description: "Analyze differences between AI agent's fix and ground truth",
    requiresGroundTruth: true,
    template: (ctx) => {
      const gtSection = ctx.groundTruthContent
        ? `\n\n<ground-truth-patch>\n${ctx.groundTruthContent}\n</ground-truth-patch>`
        : ""

      return (
        `An AI agent has attempted to fix a bug in this directory (${ctx.sourceDir}). ` +
        `The ground truth reference fix is provided below.${gtSection}\n\n` +
        `Please analyze both approaches:\n` +
        `1. Compare the agent's changes (use git diff) against the ground truth above\n` +
        `2. Identify any differences in methodology or implementation\n` +
        `3. Highlight what the agent did well and what could be improved\n` +
        `4. Assess whether the agent's fix addresses the root cause\n` +
        `5. Provide insights on the quality and correctness of the agent's fix\n\n` +
        `Be specific and cite code examples where relevant.`
      )
    },
  },
  {
    id: "analyze-quality",
    label: "Analyze Bug Fix Quality",
    icon: "🐛",
    description: "Evaluate the quality and completeness of the fix",
    template: (ctx) =>
      `Please review the recent code changes in ${ctx.sourceDir} made by an AI agent to fix a bug.\n\n` +
      `Evaluate the following aspects:\n` +
      `1. Does the fix address the root cause of the bug?\n` +
      `2. Are there any edge cases or scenarios not handled?\n` +
      `3. Code quality and adherence to ${ctx.language} best practices\n` +
      `4. Potential side effects or regressions introduced by the changes\n` +
      `5. Test coverage and error handling\n\n` +
      `Provide a detailed analysis with specific examples from the code.`,
  },
  {
    id: "review-changes",
    label: "Review Code Changes",
    icon: "📝",
    description: "General code review of all changes",
    template: (ctx) =>
      `Please conduct a thorough code review of the changes in ${ctx.sourceDir}.\n\n` +
      `Focus on:\n` +
      `1. Code quality and readability\n` +
      `2. Maintainability and extensibility\n` +
      `3. Potential bugs or logic errors\n` +
      `4. Adherence to ${ctx.language} best practices and idioms\n` +
      `5. Performance considerations\n` +
      `6. Security implications (if any)\n\n` +
      `Provide constructive feedback with specific code examples.`,
  },
  {
    id: "suggest-improvements",
    label: "Suggest Improvements",
    icon: "✨",
    description: "Get suggestions for improving the fix",
    template: (ctx) =>
      `Review the code changes in ${ctx.sourceDir} and suggest concrete improvements.\n\n` +
      `Consider:\n` +
      `1. Better error handling and edge case coverage\n` +
      `2. Performance optimizations\n` +
      `3. Code clarity and documentation\n` +
      `4. Alternative approaches that might be more robust\n` +
      `5. Opportunities to reduce complexity\n\n` +
      `For each suggestion, explain why it would be an improvement and provide example code if helpful.`,
  },
  {
    id: "explain-changes",
    label: "Explain Changes",
    icon: "💡",
    description: "Get a clear explanation of what was changed and why",
    template: (ctx) =>
      `Please analyze the code changes in ${ctx.sourceDir} and provide a clear explanation.\n\n` +
      `Include:\n` +
      `1. Summary of what files were modified\n` +
      `2. Description of the key changes made\n` +
      `3. The likely intent or purpose of each major change\n` +
      `4. How these changes work together to address the issue\n` +
      `5. Any notable design decisions or patterns used\n\n` +
      `Explain in a way that would help someone understand the fix without seeing the original bug.`,
  },
  {
    id: "find-issues",
    label: "Find Potential Issues",
    icon: "🔍",
    description: "Look for bugs, vulnerabilities, or problems",
    template: (ctx) =>
      `Please carefully examine the code changes in ${ctx.sourceDir} and identify potential issues.\n\n` +
      `Look for:\n` +
      `1. Logic errors or bugs\n` +
      `2. Security vulnerabilities\n` +
      `3. Resource leaks (memory, file handles, etc.)\n` +
      `4. Race conditions or concurrency issues\n` +
      `5. Incomplete error handling\n` +
      `6. Breaking changes to APIs\n\n` +
      `For each issue found, explain the problem, its potential impact, and suggest how to fix it.`,
  },
]

/**
 * Get available presets based on context
 * Filters out presets that require ground truth if it's not available
 */
export function getAvailablePresets(
  groundTruthAvailable: boolean
): DebugPreset[] {
  return debugPresets.filter(
    (preset) => !preset.requiresGroundTruth || groundTruthAvailable
  )
}
