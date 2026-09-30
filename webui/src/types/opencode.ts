/**
 * OpenCode SDK Types
 *
 * Type definitions for OpenCode server API responses
 */

// =============================================================================
// Session Types
// =============================================================================

export interface OpenCodeSession {
  id: string
  title?: string
  model?: {
    providerID: string
    modelID: string
  }
  project?: {
    path: string
  }
  time?: {
    created: number // Unix timestamp in milliseconds
    updated?: number
  }
}

// =============================================================================
// Message Types
// =============================================================================

export interface OpenCodeMessage {
  info: MessageInfo
  parts: MessagePart[]
}

/** What OpenCode reports when a message fails, for example a provider error */
export interface OpenCodeErrorInfo {
  name: string
  data?: {
    message?: string
    statusCode?: number
    responseBody?: string
  }
}

interface MessageInfo {
  id: string
  sessionID: string
  role: "user" | "assistant"
  /** Set on an assistant message that failed */
  error?: OpenCodeErrorInfo
  time: {
    created: number // Unix timestamp in milliseconds
    completed?: number
  }
  tokens?: {
    input: number
    output: number
  }
}

// Message parts - content blocks within a message
export type MessagePart =
  | TextPart
  | ThinkingPart
  | ToolUsePart
  | ToolResultPart
  | ToolPart
  | ReasoningPart

interface TextPart {
  type: "text"
  text: string
}

interface ThinkingPart {
  type: "thinking"
  thinking: string
}

interface ToolUsePart {
  type: "tool_use"
  id: string
  name: string
  input: Record<string, unknown>
}

interface ToolResultPart {
  type: "tool_result"
  tool_use_id: string
  content: string
  is_error?: boolean
}

// =============================================================================
// Tool Execution Types (Real-time streaming)
// =============================================================================

type ToolStatus = "pending" | "running" | "completed" | "error"

interface ToolState {
  status: ToolStatus
  input?: Record<string, unknown>
  output?: string
  error?: string
  time?: {
    start: number
    end?: number
  }
}

interface ToolPart {
  type: "tool"
  id: string
  callID: string
  tool: string // Tool name: "bash", "edit", "read", "write", "glob", "grep", etc.
  state: ToolState
}

// =============================================================================
// Reasoning Types (AI thinking process)
// =============================================================================

interface ReasoningPart {
  type: "reasoning"
  id: string
  text: string
  time?: {
    start: number
    end?: number
  }
}

// =============================================================================
// API Request/Response Types
// =============================================================================

export interface CreateSessionResponse {
  id: string
  title?: string
  model?: {
    providerID: string
    modelID: string
  }
  project?: {
    path: string
  }
}

export interface SendMessageResponse {
  info: MessageInfo
  parts: MessagePart[]
}

export interface HealthResponse {
  healthy: boolean
  /** The assistant's model when it goes through the LiteLLM proxy; absent when it needs your own key */
  proxyModel?: string
  version?: string
  processRunning?: boolean
  pid?: number
  uptime?: number
}

// =============================================================================
// Session List Types
// =============================================================================

export interface OpenCodeSessionListItem {
  id: string
  projectID: string
  directory: string
  title: string
  version: string
  parentID?: string
  summary?: {
    additions: number
    deletions: number
    files: number
  }
  share?: {
    url: string
  }
}

// =============================================================================
// Error Types
// =============================================================================

export interface OpenCodeError {
  error: string
  details?: string
}

// =============================================================================
// UI State Types
// =============================================================================

/**
 * Represents a tool execution for UI display
 */
export interface ToolExecution {
  id: string
  messageID: string
  callID: string
  tool: string
  status: ToolStatus
  input?: Record<string, unknown>
  output?: string
  error?: string
  startTime?: number
  endTime?: number
}

/**
 * Represents a pending permission request for UI display
 */
export interface PendingPermission {
  id: string
  sessionID: string
  permission: string
  patterns: string[]
  metadata?: Record<string, unknown>
  createdAt: number
}

/**
 * Represents reasoning content for UI display
 */
export interface ReasoningContent {
  id: string
  messageID: string
  text: string
  startTime?: number
  endTime?: number
}
