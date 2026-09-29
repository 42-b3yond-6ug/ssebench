/**
 * OpenCode Client - Frontend wrapper for OpenCode SDK API
 *
 * Provides a simple interface to interact with OpenCode server via backend proxy.
 */

import type {
  OpenCodeSession,
  OpenCodeMessage,
  CreateSessionResponse,
  SendMessageResponse,
  HealthResponse,
  OpenCodeError,
  OpenCodeSessionListItem,
} from "../types/opencode"
import type { DialogEntry } from "../types/container"
import { apiFetch } from "./api"

/**
 * OpenCode client for a specific container
 */
export class OpenCodeClient {
  constructor(private containerId: string) {}

  /**
   * Check if OpenCode server is healthy
   */
  async checkHealth(): Promise<HealthResponse> {
    const response = await apiFetch(
      `/api/containers/${this.containerId}/opencode/health`
    )
    return response.json()
  }

  /**
   * Create a new OpenCode session
   *
   * @param title Optional session title
   * @param workingDir Working directory for the session
   * @param apiKey Anthropic API key
   * @returns Session ID
   */
  async createSession(
    title?: string,
    workingDir?: string,
    apiKey?: string
  ): Promise<CreateSessionResponse> {
    const response = await apiFetch(
      `/api/containers/${this.containerId}/opencode/sessions`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title, workingDir, apiKey }),
      }
    )

    if (!response.ok) {
      const error: OpenCodeError = await response.json()
      throw new Error(error.error || "Failed to create session")
    }

    return response.json()
  }

  /**
   * Send a message to a session
   *
   * @param sessionId Session ID
   * @param message Message text
   * @returns Assistant response
   */
  async sendMessage(
    sessionId: string,
    message: string,
    directory?: string
  ): Promise<SendMessageResponse> {
    const response = await apiFetch(
      `/api/containers/${this.containerId}/opencode/sessions/${sessionId}/messages`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, directory }),
      }
    )

    if (!response.ok) {
      const error: OpenCodeError = await response.json()

      // Handle 404 specially - session doesn't exist
      if (response.status === 404) {
        throw new Error(
          "Session expired or no longer exists. Please start a new conversation."
        )
      }

      throw new Error(error.error || "Failed to send message")
    }

    return response.json()
  }

  /**
   * Get all messages in a session
   *
   * @param sessionId Session ID
   * @returns Array of messages
   */
  async getMessages(sessionId: string): Promise<OpenCodeMessage[]> {
    const response = await apiFetch(
      `/api/containers/${this.containerId}/opencode/sessions/${sessionId}/messages`
    )

    if (!response.ok) {
      const error: OpenCodeError = await response.json()

      // Handle 404 specially - session doesn't exist
      if (response.status === 404) {
        throw new Error("Session not found")
      }

      throw new Error(error.error || "Failed to get messages")
    }

    const data = await response.json()
    return data.messages || data
  }

  /**
   * Get session details
   *
   * @param sessionId Session ID
   * @returns Session object
   */
  async getSession(sessionId: string): Promise<OpenCodeSession> {
    const response = await apiFetch(
      `/api/containers/${this.containerId}/opencode/sessions/${sessionId}`
    )

    if (!response.ok) {
      const error: OpenCodeError = await response.json()
      throw new Error(error.error || "Failed to get session")
    }

    return response.json()
  }

  /**
   * Delete a session
   *
   * @param sessionId Session ID
   */
  async deleteSession(sessionId: string): Promise<void> {
    const response = await apiFetch(
      `/api/containers/${this.containerId}/opencode/sessions/${sessionId}`,
      {
        method: "DELETE",
      }
    )

    if (!response.ok) {
      const error: OpenCodeError = await response.json()
      throw new Error(error.error || "Failed to delete session")
    }
  }

  /**
   * List all sessions for this container
   *
   * @param directory Optional working directory to filter sessions
   * @returns Array of session list items
   */
  async listSessions(directory?: string): Promise<OpenCodeSessionListItem[]> {
    const url = directory
      ? `/api/containers/${this.containerId}/opencode/sessions?directory=${encodeURIComponent(directory)}`
      : `/api/containers/${this.containerId}/opencode/sessions`

    const response = await apiFetch(url)

    if (!response.ok) {
      const error: OpenCodeError = await response.json()
      throw new Error(error.error || "Failed to list sessions")
    }

    const data = await response.json()
    return data.sessions || data || []
  }

  /**
   * Reply to a permission request
   *
   * @param sessionId Session ID
   * @param permissionId Permission request ID
   * @param allow Whether to allow the permission
   */
  async replyToPermission(
    sessionId: string,
    permissionId: string,
    allow: boolean
  ): Promise<void> {
    const response = await apiFetch(
      `/api/containers/${this.containerId}/opencode/sessions/${sessionId}/permissions/${permissionId}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ allow }),
      }
    )

    if (!response.ok) {
      const error: OpenCodeError = await response.json()
      throw new Error(error.error || "Failed to reply to permission")
    }
  }
}

/**
 * Transform OpenCode messages to DialogEntry format
 *
 * This allows us to reuse the AgentPanel rendering components.
 *
 * @param messages OpenCode messages
 * @returns Array of DialogEntry objects
 */
export function transformToDialogEntries(
  messages: OpenCodeMessage[]
): DialogEntry[] {
  const entries: DialogEntry[] = []
  let seq = 0

  for (const message of messages) {
    const { info, parts } = message

    // If this is a user message with text, create a PromptEntry
    if (info.role === "user") {
      const textParts = parts.filter((p) => p.type === "text")
      if (textParts.length > 0) {
        entries.push({
          type: "prompt",
          seq: seq++,
          ts: new Date(info.time.created).toISOString(),
          content: textParts.map((p) => (p as any).text).join("\n"),
        })
      }
      continue
    }

    // Process assistant message parts
    const timestamp = new Date(info.time.created).toISOString()

    for (const part of parts) {
      switch (part.type) {
        case "text":
          entries.push({
            type: "message",
            seq: seq++,
            ts: timestamp,
            role: "assistant",
            content: part.text,
            tokens: info.tokens
              ? {
                  in: info.tokens.input,
                  out: info.tokens.output,
                }
              : undefined,
          })
          break

        case "thinking":
          entries.push({
            type: "thinking",
            seq: seq++,
            ts: timestamp,
            content: part.thinking,
          })
          break

        case "tool_use":
          // Create a running tool entry
          entries.push({
            type: "tool",
            seq: seq++,
            ts: timestamp,
            tool_id: part.id,
            name: part.name,
            status: "running",
            args: part.input,
          })
          break

        case "tool_result":
          // Find the matching tool_use entry and update it
          const toolEntry = entries.find(
            (e) =>
              e.type === "tool" &&
              e.tool_id === part.tool_use_id &&
              e.status === "running"
          )
          if (toolEntry && toolEntry.type === "tool") {
            toolEntry.status = part.is_error ? "error" : "success"
            toolEntry.result = part.is_error ? undefined : part.content
            toolEntry.error = part.is_error ? part.content : undefined
          } else {
            // If no matching tool_use found, create a new entry
            entries.push({
              type: "tool",
              seq: seq++,
              ts: timestamp,
              tool_id: part.tool_use_id,
              name: "unknown",
              status: part.is_error ? "error" : "success",
              result: part.is_error ? undefined : part.content,
              error: part.is_error ? part.content : undefined,
            })
          }
          break

        case "tool":
          // Streaming tool part - has full state info
          const toolPart = part as any
          const statusMap: Record<string, "running" | "success" | "error"> = {
            pending: "running",
            running: "running",
            completed: "success",
            error: "error",
          }
          entries.push({
            type: "tool",
            seq: seq++,
            ts: timestamp,
            tool_id: toolPart.callID || toolPart.id,
            name: toolPart.tool,
            status: statusMap[toolPart.state?.status] || "running",
            args: toolPart.state?.input,
            result: toolPart.state?.output,
            error: toolPart.state?.error,
          })
          break
      }
    }
  }

  return entries
}
