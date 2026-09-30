/**
 * Routes the OpenCode debugging assistant through the run's LiteLLM proxy.
 *
 * A container on the default `restricted` network reaches the proxy but not
 * the internet, so the assistant cannot call a provider directly there. The
 * container knows the proxy's URL and the run's model (SSE_BASE_URL,
 * SSE_MODEL_NAME). The assistant gets a key of its own from the proxy, not the
 * run's: what it spends must not count as the run's spend, which the run's
 * summary records.
 */

import { existsSync, readFileSync } from "fs"
import { join } from "path"
import { ssebenchPath } from "./config"
import { containerEnv } from "./runner"

/** What one assistant key may spend, in dollars */
export const ASSISTANT_BUDGET = 5

export interface AssistantProvider {
  /** The proxy's URL from inside the run container */
  baseUrl: string
  apiKey: string
  model: string
}

/** A setting from the environment, else from `.env` in the checkout */
function setting(name: string): string {
  const fromEnv = process.env[name]?.trim()
  if (fromEnv) return fromEnv
  const file = join(ssebenchPath(), ".env")
  if (!existsSync(file)) return ""
  for (const line of readFileSync(file, "utf-8").split("\n")) {
    const match = line.match(
      /^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/
    )
    if (match?.[1] !== name) continue
    const value = match[2]
    return /^(["']).*\1$/.test(value) ? value.slice(1, -1) : value
  }
  return ""
}

/** The proxy's address from the host, where this server runs */
function hostUrl(): string {
  return `http://127.0.0.1:${setting("LITELLM_PORT") || "4000"}`
}

const keys = new Map<string, string>()

/**
 * The provider for a container's assistant: the run's model through its
 * proxy, with a key made for the assistant. Null when the container has no
 * model (a reference run, or a sidecar run's task container) or the proxy's
 * admin key is unavailable, in which case the assistant uses the user's own
 * provider key.
 */
export async function proxyProviderFor(
  containerId: string
): Promise<AssistantProvider | null> {
  const env = await containerEnv(containerId, [
    "SSE_BASE_URL",
    "SSE_MODEL_NAME",
  ])
  const baseUrl = env?.SSE_BASE_URL
  const model = env?.SSE_MODEL_NAME
  if (!baseUrl || !model) return null
  const master = setting("LITELLM_MASTER_KEY")
  if (!master) return null

  let apiKey = keys.get(containerId)
  if (!apiKey) {
    try {
      const response = await fetch(`${hostUrl()}/key/generate`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${master}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          models: [model],
          max_budget: ASSISTANT_BUDGET,
          // Aliases are unique across the proxy's keys, and a restarted
          // server asks again for the same container.
          key_alias: `webui-assistant-${containerId.slice(0, 12)}-${crypto.randomUUID().slice(0, 8)}`,
        }),
        signal: AbortSignal.timeout(10_000),
      })
      if (!response.ok) {
        console.error(
          `[OpenCode] The proxy refused to make an assistant key: ${response.status}`
        )
        return null
      }
      apiKey = ((await response.json()) as { key?: string }).key
    } catch (error) {
      console.error("[OpenCode] Could not reach the proxy:", error)
      return null
    }
    if (!apiKey) return null
    keys.set(containerId, apiKey)
  }
  return { baseUrl, apiKey, model }
}

/**
 * The OpenCode configuration that makes `provider` the assistant's only
 * model, as an OpenAI-compatible endpoint.
 */
export function buildAssistantConfig(provider: AssistantProvider) {
  return {
    provider: {
      ssebench: {
        npm: "@ai-sdk/openai-compatible",
        name: "SSEBench LiteLLM",
        options: {
          baseURL: provider.baseUrl.replace(/\/+$/, "") + "/v1",
          apiKey: provider.apiKey,
        },
        models: { [provider.model]: { name: provider.model } },
      },
    },
    model: `ssebench/${provider.model}`,
  }
}
