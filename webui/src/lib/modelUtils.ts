/**
 * Model Utilities - Helper functions for model grouping and parsing
 */

type VendorName = "anthropic" | "openai" | "google" | "unknown"

interface ModelGroup {
  vendor: VendorName
  vendorDisplayName: string
  models: string[]
}

/**
 * Parse vendor name from model string
 */
function getVendorFromModel(model: string): VendorName {
  const lower = model.toLowerCase()
  if (lower.startsWith("claude-")) return "anthropic"
  if (lower.startsWith("gpt-")) return "openai"
  if (lower.startsWith("gemini-")) return "google"
  return "unknown"
}

/**
 * Get display name for vendor
 */
function getVendorDisplayName(vendor: VendorName): string {
  switch (vendor) {
    case "anthropic":
      return "Anthropic"
    case "openai":
      return "OpenAI"
    case "google":
      return "Google"
    default:
      return "Other"
  }
}

/**
 * Clean model name for display
 * Examples:
 *   claude-opus-4-5 → "Opus 4-5"
 *   gpt-5.2 → "GPT 5.2"
 *   gemini-3-flash → "Gemini 3 Flash"
 */
export function cleanModelName(model: string): string {
  // Claude models
  if (model.startsWith("claude-")) {
    const parts = model.replace("claude-", "").split("-")
    if (parts.length >= 2) {
      // Capitalize first part (opus, sonnet, haiku)
      const tier = parts[0].charAt(0).toUpperCase() + parts[0].slice(1)
      // Join rest as version (4-5, 4-0, etc.)
      const version = parts.slice(1).join("-")
      return `${tier} ${version}`
    }
  }

  // GPT models
  if (model.startsWith("gpt-")) {
    const parts = model.replace("gpt-", "").split("-")
    const version = parts[0]
    const suffix = parts.slice(1).join(" ")
    if (suffix) {
      // Capitalize suffix (codex, codex-max)
      const capitalizedSuffix = suffix
        .split("-")
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ")
      return `GPT ${version} ${capitalizedSuffix}`
    }
    return `GPT ${version}`
  }

  // Gemini models
  if (model.startsWith("gemini-")) {
    const parts = model.replace("gemini-", "").split("-")
    if (parts.length >= 2) {
      const version = parts[0]
      const tier = parts
        .slice(1)
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ")
      return `Gemini ${version} ${tier}`
    }
  }

  // Fallback: just return as-is
  return model
}

/**
 * Group models by vendor
 */
export function groupModelsByVendor(models: string[]): ModelGroup[] {
  const groups = new Map<VendorName, string[]>()

  for (const model of models) {
    const vendor = getVendorFromModel(model)
    if (!groups.has(vendor)) {
      groups.set(vendor, [])
    }
    groups.get(vendor)!.push(model)
  }

  // Convert to array and sort by vendor preference
  const vendorOrder: VendorName[] = ["anthropic", "openai", "google", "unknown"]
  const result: ModelGroup[] = []

  for (const vendor of vendorOrder) {
    if (groups.has(vendor)) {
      result.push({
        vendor,
        vendorDisplayName: getVendorDisplayName(vendor),
        models: groups.get(vendor)!.sort(),
      })
    }
  }

  return result
}

/**
 * Helper function to detect vendor from model/agent name
 */
export function getVendorFromName(name: string): VendorName {
  const lower = name.toLowerCase()

  // Models
  if (lower.startsWith("claude")) return "anthropic"
  if (lower.startsWith("gpt") || lower.startsWith("codex")) return "openai"
  if (lower.startsWith("gemini")) return "google"

  // Agents
  if (lower.includes("claude")) return "anthropic"
  if (lower.includes("codex") || lower.includes("openai")) return "openai"

  return "unknown"
}
