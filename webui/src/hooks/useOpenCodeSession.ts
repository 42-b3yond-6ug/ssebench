/**
 * useOpenCodeSession Hook
 *
 * Manages OpenCode chat session state and operations with real-time streaming
 */

import { useState, useEffect, useCallback, useMemo, useRef } from "react"
import { OpenCodeClient, transformToDialogEntries } from "../lib/opencodeClient"
import type {
  OpenCodeMessage,
  MessagePart,
  ToolExecution,
  PendingPermission,
  ReasoningContent,
} from "../types/opencode"
import type { DialogEntry } from "../types/container"
import { useSettings } from "../context/SettingsContext"
import { useOpenCodeEvents } from "./useOpenCodeEvents"

interface UseOpenCodeSessionOptions {
  containerId: string
  workingDir?: string
  sessionId?: string // Existing session ID to load
  initialMessage?: string
  autoCreate?: boolean
}

interface UseOpenCodeSessionResult {
  // Session state
  sessionId: string | null
  messages: OpenCodeMessage[]
  dialogEntries: DialogEntry[]
  isLoading: boolean
  error: string | null
  isHealthy: boolean

  // Connection state
  isConnecting: boolean
  isProcessRunning: boolean

  // Streaming state
  isStreaming: boolean
  streamingMessageId: string | null

  // Tool execution state
  toolExecutions: Map<string, ToolExecution>
  activeTools: ToolExecution[]

  // Permission state
  pendingPermissions: PendingPermission[]
  allowedPermissions: Set<string> // Cached "Always Allow" permissions for this session

  // Reasoning state
  reasoningContent: Map<string, ReasoningContent>

  // Operations
  sendMessage: (message: string) => Promise<void>
  createSession: () => Promise<void>
  refreshMessages: () => Promise<void>
  reset: () => void
  replyToPermission: (
    id: string,
    allow: boolean,
    alwaysAllow?: boolean
  ) => Promise<void>

  // API key management
  hasApiKey: boolean
  needsApiKey: boolean
}

/**
 * Hook to manage OpenCode session
 */
export function useOpenCodeSession({
  containerId,
  workingDir,
  sessionId: existingSessionId,
  initialMessage,
  autoCreate = true,
}: UseOpenCodeSessionOptions): UseOpenCodeSessionResult {
  const { anthropicApiKey, hasAnthropicApiKey } = useSettings()

  const [sessionId, setSessionId] = useState<string | null>(
    existingSessionId || null
  )
  const [messages, setMessages] = useState<OpenCodeMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isHealthy, setIsHealthy] = useState(false)
  const [isInitializing, setIsInitializing] = useState(true)
  const [isConnecting, setIsConnecting] = useState(false)
  const [isProcessRunning, setIsProcessRunning] = useState(false)

  // Streaming state
  const [streamingMessages, setStreamingMessages] = useState<
    Map<string, Map<string, string>>
  >(new Map()) // messageId -> partId -> text
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(
    null
  )
  const [isStreaming, setIsStreaming] = useState(false)

  // Track pending user message to avoid showing it as assistant message
  const pendingUserMessageRef = useRef<string | null>(null)

  // Tool execution state
  const [toolExecutions, setToolExecutions] = useState<
    Map<string, ToolExecution>
  >(new Map())

  // Permission state
  const [pendingPermissions, setPendingPermissions] = useState<
    PendingPermission[]
  >([])
  const [allowedPermissions, setAllowedPermissions] = useState<Set<string>>(
    new Set()
  )

  // Reasoning state
  const [reasoningContent, setReasoningContent] = useState<
    Map<string, ReasoningContent>
  >(new Map())

  const client = useMemo(() => new OpenCodeClient(containerId), [containerId])

  const hasApiKey = hasAnthropicApiKey()
  const needsApiKey = !hasApiKey && !sessionId

  // Handle streaming message part updates
  const handleMessagePartUpdate = useCallback(
    (messageId: string, partId: string, _delta: string, fullText: string) => {
      console.log(
        `[OpenCode] Streaming update - message: ${messageId}, part: ${partId}, text length: ${fullText.length}`
      )

      setStreamingMessageId(messageId)
      setIsStreaming(true)

      setStreamingMessages((prev) => {
        const updated = new Map(prev)
        const messageParts = updated.get(messageId) || new Map()
        messageParts.set(partId, fullText)
        updated.set(messageId, messageParts)
        return updated
      })
    },
    []
  )

  // Handle message completion
  const handleMessageComplete = useCallback(
    (messageId: string) => {
      console.log(`[OpenCode] Message complete: ${messageId}`)

      // Clear streaming state for this message
      setStreamingMessages((prev) => {
        const updated = new Map(prev)
        updated.delete(messageId)

        // If no more streaming messages, reset streaming state
        if (updated.size === 0) {
          setIsStreaming(false)
          setStreamingMessageId(null)
        }

        return updated
      })

      // Also check streamingMessageId directly
      setStreamingMessageId((current) => {
        if (current === messageId) {
          setIsStreaming(false)
          return null
        }
        return current
      })

      // Refresh messages to get final state
      if (sessionId) {
        refreshMessagesInternal(sessionId)
      }
    },
    [sessionId]
  )

  // Memoize event callbacks to prevent unnecessary reconnections
  const handleSessionStatus = useCallback(
    (status: "idle" | "busy" | "retry") => {
      console.log(`[OpenCode] Session status: ${status}`)
      if (status === "busy") {
        setIsStreaming(true)
      } else if (status === "idle") {
        setIsStreaming(false)
      }
    },
    []
  )

  const handleEventError = useCallback((err: Error) => {
    console.error("[OpenCode] Event stream error:", err)
    // Don't set error state - fallback to polling
  }, [])

  // Handle tool execution updates
  const handleToolUpdate = useCallback((tool: ToolExecution) => {
    console.log(`[OpenCode] Tool update: ${tool.tool} (${tool.status})`)
    setToolExecutions((prev) => {
      const updated = new Map(prev)
      updated.set(tool.id, tool)
      return updated
    })
  }, [])

  // Handle permission request
  const handlePermissionAsked = useCallback((permission: PendingPermission) => {
    console.log(
      `[OpenCode] Permission asked: ${permission.permission}`,
      permission.patterns
    )

    // Check if this permission type is in our "Always Allow" list
    // Note: We don't auto-allow here - the permission dialog will check and auto-reply
    setPendingPermissions((prev) => {
      // Don't add duplicates
      if (prev.some((p) => p.id === permission.id)) {
        return prev
      }
      return [...prev, permission]
    })
  }, [])

  // Handle permission reply (from server acknowledgement)
  const handlePermissionReplied = useCallback((id: string, _allow: boolean) => {
    console.log(`[OpenCode] Permission replied: ${id}`)
    // Remove from pending list
    setPendingPermissions((prev) => prev.filter((p) => p.id !== id))
  }, [])

  // Handle reasoning content updates
  const handleReasoningUpdate = useCallback((reasoning: ReasoningContent) => {
    console.log(
      `[OpenCode] Reasoning update: ${reasoning.id.slice(0, 8)}...`,
      reasoning.text.slice(0, 50)
    )
    setReasoningContent((prev) => {
      const updated = new Map(prev)
      updated.set(reasoning.id, reasoning)
      return updated
    })
  }, [])

  // Subscribe to WebSocket events for real-time updates
  useOpenCodeEvents({
    containerId,
    sessionId,
    directory: workingDir,
    enabled: !!sessionId && isHealthy,
    onMessagePartUpdate: handleMessagePartUpdate,
    onMessageComplete: handleMessageComplete,
    onSessionStatus: handleSessionStatus,
    onToolUpdate: handleToolUpdate,
    onPermissionAsked: handlePermissionAsked,
    onPermissionReplied: handlePermissionReplied,
    onReasoningUpdate: handleReasoningUpdate,
    onError: handleEventError,
  })

  // Check health on mount and poll while connecting
  useEffect(() => {
    let mounted = true
    let pollInterval: NodeJS.Timeout | null = null

    const checkHealth = async () => {
      try {
        const health = await client.checkHealth()
        if (mounted) {
          setIsHealthy(health.healthy)
          setIsProcessRunning(health.processRunning || false)
          setIsInitializing(false)

          // If process is running but not healthy, we're connecting
          if (health.processRunning && !health.healthy) {
            setIsConnecting(true)
          } else {
            setIsConnecting(false)
          }

          // Keep polling if we're still connecting
          if (health.processRunning && !health.healthy && !pollInterval) {
            pollInterval = setInterval(() => {
              checkHealth()
            }, 2000) // Poll every 2 seconds while connecting
          } else if (health.healthy && pollInterval) {
            // Stop polling once connected
            clearInterval(pollInterval)
            pollInterval = null
          }
        }
      } catch (err) {
        console.error("[OpenCode] Health check failed:", err)
        if (mounted) {
          setIsHealthy(false)
          setIsProcessRunning(false)
          setIsConnecting(false)
          setIsInitializing(false)
        }
      }
    }

    checkHealth()

    return () => {
      mounted = false
      if (pollInterval) {
        clearInterval(pollInterval)
      }
    }
  }, [client])

  // Load messages for existing session
  useEffect(() => {
    if (existingSessionId && isHealthy) {
      console.log("[OpenCode] Loading existing session:", existingSessionId)
      setSessionId(existingSessionId)

      // Try to load messages, if session doesn't exist, clear it
      refreshMessagesInternal(existingSessionId).catch((err) => {
        console.error("[OpenCode] Failed to load session:", err)
        if (err.message?.includes("Session not found")) {
          console.log("[OpenCode] Session not found, clearing")
          setSessionId(null)
          setError(
            "This session no longer exists. Please start a new conversation."
          )
        }
      })
    }
  }, [existingSessionId, isHealthy])

  // Create session on mount if autoCreate is enabled
  useEffect(() => {
    if (!autoCreate || sessionId || !isHealthy || isInitializing) return
    if (!hasApiKey) {
      setError("Please set your Anthropic API key in Settings")
      return
    }

    createSessionInternal()
  }, [autoCreate, sessionId, isHealthy, isInitializing, hasApiKey])

  const createSessionInternal = async () => {
    if (!hasApiKey) {
      setError("Please set your Anthropic API key in Settings")
      return
    }

    setIsLoading(true)
    setError(null)

    try {
      console.log("[OpenCode] Creating session...")
      const session = await client.createSession(
        "Debug Session",
        workingDir,
        anthropicApiKey || undefined
      )
      console.log("[OpenCode] Session created:", session.id)
      setSessionId(session.id)

      // Send initial message if provided
      if (initialMessage && session.id) {
        console.log("[OpenCode] Sending initial message...")
        await sendMessageInternal(session.id, initialMessage)
      }
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Failed to create session"
      console.error("[OpenCode] Session creation failed:", errorMessage)
      setError(errorMessage)
    } finally {
      setIsLoading(false)
    }
  }

  const sendMessageInternal = async (sid: string, message: string) => {
    // Track the user message to avoid showing it as assistant message in streaming
    pendingUserMessageRef.current = message

    // Clear previous streaming state for new message
    setToolExecutions(new Map())
    setReasoningContent(new Map())

    // Optimistic update: Add user message immediately to UI
    const optimisticUserMessage: OpenCodeMessage = {
      info: {
        id: `temp-${Date.now()}`,
        sessionID: sid,
        role: "user" as const,
        time: {
          created: Date.now(),
        },
      },
      parts: [
        {
          type: "text" as const,
          text: message,
        },
      ],
    }

    // Add to messages list immediately for instant feedback
    setMessages((prev) => [...prev, optimisticUserMessage])

    try {
      // Send message asynchronously - don't wait for completion
      // Real-time updates will come via WebSocket streaming
      // Pass workingDir so the server knows which directory context to use
      client
        .sendMessage(sid, message, workingDir)
        .then((response) => {
          console.log("[OpenCode] Message sent, response:", response)

          // The response contains the complete assistant message
          // This means AI has finished generating - reset streaming state
          setIsStreaming(false)
          setStreamingMessageId(null)
          setStreamingMessages(new Map())
          setToolExecutions(new Map()) // Clear tool executions after completion
          setReasoningContent(new Map()) // Clear reasoning after completion
          pendingUserMessageRef.current = null

          // Refresh messages to get the final state with real IDs
          refreshMessagesInternal(sid)
        })
        .catch((err) => {
          console.error("[OpenCode] Async send failed:", err)
          // Reset streaming state on error too
          setIsStreaming(false)
          setStreamingMessageId(null)
          setStreamingMessages(new Map())
          setToolExecutions(new Map()) // Clear tool executions on error
          setReasoningContent(new Map()) // Clear reasoning on error
          pendingUserMessageRef.current = null

          // Remove optimistic message on error
          setMessages((prev) =>
            prev.filter((m) => m.info.id !== optimisticUserMessage.info.id)
          )
          setError(
            err instanceof Error ? err.message : "Failed to send message"
          )
        })

      // Don't refresh immediately - keep the optimistic message visible
      // The refresh will happen when the send completes
    } catch (err) {
      // Remove optimistic message on error
      setMessages((prev) =>
        prev.filter((m) => m.info.id !== optimisticUserMessage.info.id)
      )

      const errorMessage =
        err instanceof Error ? err.message : "Failed to send message"
      console.error("[OpenCode] Send message failed:", errorMessage)
      throw err
    }
  }

  const refreshMessagesInternal = async (sid: string) => {
    try {
      const msgs = await client.getMessages(sid)
      console.log("[OpenCode] Messages refreshed:", msgs.length)
      setMessages(msgs)

      // Clear pending user message after refresh
      pendingUserMessageRef.current = null

      // Check if we should reset streaming state
      // If there are no streaming messages left, we're done streaming
      setStreamingMessages((prev) => {
        if (prev.size === 0) {
          setIsStreaming(false)
          setStreamingMessageId(null)
        }
        return prev
      })
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Failed to refresh messages"
      console.error("[OpenCode] Refresh messages failed:", errorMessage)
      throw err
    }
  }

  const createSession = useCallback(async () => {
    await createSessionInternal()
  }, [client, workingDir, initialMessage, anthropicApiKey, hasApiKey])

  const sendMessage = useCallback(
    async (message: string) => {
      if (!sessionId) {
        setError("No active session")
        return
      }

      setIsLoading(true)
      setError(null)

      try {
        await sendMessageInternal(sessionId, message)
      } catch (err) {
        const errorMessage =
          err instanceof Error ? err.message : "Failed to send message"

        // If session expired, clear it so user can start fresh
        if (
          errorMessage.includes("expired") ||
          errorMessage.includes("no longer exists")
        ) {
          console.error("[OpenCode] Session expired, clearing session ID")
          setSessionId(null)
          setMessages([])
        }

        setError(errorMessage)
      } finally {
        setIsLoading(false)
      }
    },
    [sessionId]
  )

  const refreshMessages = useCallback(async () => {
    if (!sessionId) return

    try {
      await refreshMessagesInternal(sessionId)
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Failed to refresh messages"
      setError(errorMessage)
    }
  }, [sessionId, client])

  const reset = useCallback(() => {
    setSessionId(null)
    setMessages([])
    setError(null)
    setIsLoading(false)
    setToolExecutions(new Map())
    setPendingPermissions([])
    setReasoningContent(new Map())
    // Note: Don't reset allowedPermissions - those persist for the session
  }, [])

  // Reply to a permission request
  const replyToPermission = useCallback(
    async (id: string, allow: boolean, alwaysAllow?: boolean) => {
      if (!sessionId) return

      console.log(
        `[OpenCode] Replying to permission ${id}: allow=${allow}, alwaysAllow=${alwaysAllow}`
      )

      // If "Always Allow" was selected, add to cached permissions
      if (allow && alwaysAllow) {
        const permission = pendingPermissions.find((p) => p.id === id)
        if (permission) {
          setAllowedPermissions((prev) => {
            const updated = new Set(prev)
            updated.add(permission.permission)
            return updated
          })
        }
      }

      // Optimistically remove from pending list
      setPendingPermissions((prev) => prev.filter((p) => p.id !== id))

      // Send reply to server
      try {
        await client.replyToPermission(sessionId, id, allow)
      } catch (err) {
        console.error("[OpenCode] Failed to reply to permission:", err)
        setError(
          err instanceof Error ? err.message : "Failed to reply to permission"
        )
      }
    },
    [sessionId, pendingPermissions, client]
  )

  // Compute tools to display - show all tools while streaming, only active when idle
  const activeTools = useMemo(() => {
    const allTools = Array.from(toolExecutions.values())
    if (isStreaming) {
      // While streaming, show all tools from this session
      return allTools
    }
    // When idle, only show running tools (if any)
    return allTools.filter(
      (t) => t.status === "pending" || t.status === "running"
    )
  }, [toolExecutions, isStreaming])

  // Group tool executions by messageID
  const toolsByMessage = useMemo(() => {
    const grouped = new Map<string, ToolExecution[]>()
    toolExecutions.forEach((tool) => {
      const messageId = tool.messageID
      if (!grouped.has(messageId)) {
        grouped.set(messageId, [])
      }
      grouped.get(messageId)!.push(tool)
    })
    return grouped
  }, [toolExecutions])

  // Merge streaming messages with stored messages, including tool parts
  const displayMessages = useMemo(() => {
    // Helper to create tool parts from tool executions
    const createToolParts = (tools: ToolExecution[]): MessagePart[] => {
      return tools.map((tool) => ({
        type: "tool" as const,
        id: tool.id,
        callID: tool.callID,
        tool: tool.tool,
        state: {
          status: tool.status,
          input: tool.input,
          output: tool.output,
          error: tool.error,
          time: {
            start: tool.startTime || Date.now(),
            end: tool.endTime,
          },
        },
      }))
    }

    // First, update existing messages with streaming content and tools
    const updatedMessages = messages.map((msg) => {
      const streamingParts = streamingMessages.get(msg.info.id)
      const messageTools = toolsByMessage.get(msg.info.id)

      let updatedParts = [...msg.parts]

      // Add streaming text if present
      if (streamingParts && streamingParts.size > 0) {
        const streamingText = Array.from(streamingParts.values()).join("")
        const hasTextPart = updatedParts.some((p) => p.type === "text")
        if (hasTextPart) {
          updatedParts = updatedParts.map((part) => {
            if (part.type === "text") {
              return { ...part, text: streamingText }
            }
            return part
          })
        } else {
          updatedParts.push({ type: "text" as const, text: streamingText })
        }
      }

      // Add tool parts if present (and not already in the message)
      if (messageTools && messageTools.length > 0) {
        const existingToolIds = new Set(
          updatedParts.filter((p) => p.type === "tool").map((p) => p.id)
        )
        const newToolParts = createToolParts(
          messageTools.filter((t) => !existingToolIds.has(t.id))
        )
        updatedParts = [...updatedParts, ...newToolParts]
      }

      if (updatedParts !== msg.parts) {
        return { ...msg, parts: updatedParts }
      }
      return msg
    })

    // Check if there are streaming messages that don't exist in our messages array
    const existingMessageIds = new Set(messages.map((m) => m.info.id))
    const streamingOnlyMessages: OpenCodeMessage[] = []

    // Collect all message IDs that have streaming content or tools
    const syntheticMessageIds = new Set<string>()
    streamingMessages.forEach((_, messageId) => {
      if (!existingMessageIds.has(messageId)) {
        syntheticMessageIds.add(messageId)
      }
    })
    toolsByMessage.forEach((_, messageId) => {
      if (!existingMessageIds.has(messageId)) {
        syntheticMessageIds.add(messageId)
      }
    })

    syntheticMessageIds.forEach((messageId) => {
      const streamingParts = streamingMessages.get(messageId)
      const messageTools = toolsByMessage.get(messageId)

      const parts: MessagePart[] = []

      // Add text part if present
      if (streamingParts && streamingParts.size > 0) {
        const streamingText = Array.from(streamingParts.values()).join("")

        // Skip if this looks like the user's pending message
        const pendingMsg = pendingUserMessageRef.current
        if (pendingMsg && streamingText.trim() === pendingMsg.trim()) {
          console.log(
            "[OpenCode] Skipping synthetic message - matches pending user message"
          )
          return
        }

        parts.push({ type: "text" as const, text: streamingText })
      }

      // Add tool parts if present
      if (messageTools && messageTools.length > 0) {
        parts.push(...createToolParts(messageTools))
      }

      if (parts.length > 0) {
        streamingOnlyMessages.push({
          info: {
            id: messageId,
            sessionID: sessionId || "",
            role: "assistant" as const,
            time: { created: Date.now() },
          },
          parts,
        })
      }
    })

    // Append streaming-only messages at the end
    return [...updatedMessages, ...streamingOnlyMessages]
  }, [messages, streamingMessages, toolsByMessage, sessionId])

  // Transform messages to dialog entries for rendering
  const dialogEntries = useMemo(
    () => transformToDialogEntries(displayMessages),
    [displayMessages]
  )

  return {
    sessionId,
    messages: displayMessages,
    dialogEntries,
    isLoading: isLoading || isInitializing,
    error,
    isHealthy,
    isConnecting,
    isProcessRunning,
    isStreaming,
    streamingMessageId,
    toolExecutions,
    activeTools,
    pendingPermissions,
    allowedPermissions,
    reasoningContent,
    sendMessage,
    createSession,
    refreshMessages,
    reset,
    replyToPermission,
    hasApiKey,
    needsApiKey,
  }
}
