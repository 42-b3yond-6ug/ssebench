/**
 * Message Components - Shared rendering components for dialog entries
 *
 * These components are used by both AgentPanel and OpenCode chat interface
 * for consistent message rendering.
 */

import { useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import type {
  PromptEntry,
  MessageEntry,
  ThinkingEntry,
  ToolEntry,
} from "../../types/container"

// =============================================================================
// Utility Functions
// =============================================================================

function formatTime(ts: string): string {
  if (!ts) return "—"

  try {
    const date = new Date(ts)
    // Check if date is valid
    if (isNaN(date.getTime())) {
      return "—"
    }
    return date.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    })
  } catch {
    return "—"
  }
}

// =============================================================================
// Message Components
// =============================================================================

/** User prompt entry */
export function PromptMessage({ entry }: { entry: PromptEntry }) {
  const [isExpanded, setIsExpanded] = useState(false)
  const isLong = entry.content.length > 300

  return (
    <div className="bg-bg-2 rounded-lg p-3">
      <div className="text-fg-4 mb-2 flex items-center gap-2 text-xs">
        <svg
          className="text-gruvbox-green h-4 w-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
          />
        </svg>
        <span>You</span>
        <span className="text-fg-4/60">{formatTime(entry.ts)}</span>
      </div>
      <div className="text-fg text-sm leading-relaxed whitespace-pre-wrap">
        {isLong && !isExpanded
          ? entry.content.slice(0, 300) + "..."
          : entry.content}
      </div>
      {isLong && (
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="text-gruvbox-aqua mt-2 text-xs hover:underline"
        >
          {isExpanded ? "Show less" : "Show more"}
        </button>
      )}
    </div>
  )
}

/** Assistant message entry */
export function AssistantMessage({ entry }: { entry: MessageEntry }) {
  return (
    <div className="border-gruvbox-aqua border-l-2 pl-3">
      <div className="text-fg-4 mb-2 flex items-center gap-2 text-xs">
        <svg
          className="text-gruvbox-aqua h-4 w-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
          />
        </svg>
        <span>OpenCode</span>
        <span className="text-fg-4/60">{formatTime(entry.ts)}</span>
        {entry.tokens && (
          <span className="text-fg-4/40 ml-auto text-[10px]">
            {entry.tokens.in}↓ {entry.tokens.out}↑
          </span>
        )}
      </div>
      <div className="text-fg prose-invert prose-sm max-w-none text-sm leading-relaxed">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            // Style code blocks
            code: ({ className, children, ...props }) => {
              const isInline = !className
              if (isInline) {
                return (
                  <code
                    className="bg-bg-1 text-gruvbox-yellow rounded px-1.5 py-0.5 font-mono text-xs"
                    {...props}
                  >
                    {children}
                  </code>
                )
              }
              return (
                <code
                  className="bg-bg-1 block overflow-x-auto rounded p-2 font-mono text-xs"
                  {...props}
                >
                  {children}
                </code>
              )
            },
            // Style pre blocks (code block wrapper)
            pre: ({ children }) => (
              <pre className="bg-bg-1 my-2 overflow-x-auto rounded-lg">
                {children}
              </pre>
            ),
            // Style paragraphs
            p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
            // Style links
            a: ({ href, children }) => (
              <a
                href={href}
                className="text-gruvbox-aqua hover:underline"
                target="_blank"
                rel="noopener noreferrer"
              >
                {children}
              </a>
            ),
            // Style lists
            ul: ({ children }) => (
              <ul className="mb-2 list-inside list-disc space-y-1">
                {children}
              </ul>
            ),
            ol: ({ children }) => (
              <ol className="mb-2 list-inside list-decimal space-y-1">
                {children}
              </ol>
            ),
            li: ({ children }) => <li className="text-fg-3">{children}</li>,
            // Style headings
            h1: ({ children }) => (
              <h1 className="text-fg mb-2 text-lg font-bold">{children}</h1>
            ),
            h2: ({ children }) => (
              <h2 className="text-fg mb-2 text-base font-bold">{children}</h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-fg mb-1 text-sm font-bold">{children}</h3>
            ),
            // Style blockquotes
            blockquote: ({ children }) => (
              <blockquote className="border-gruvbox-gray text-fg-4 my-2 border-l-2 pl-3 italic">
                {children}
              </blockquote>
            ),
            // Style strong/emphasis
            strong: ({ children }) => (
              <strong className="text-fg font-semibold">{children}</strong>
            ),
            em: ({ children }) => (
              <em className="text-fg-3 italic">{children}</em>
            ),
            // Style tables (minimal borders)
            table: ({ children }) => (
              <div className="my-2 overflow-x-auto">
                <table className="min-w-full border-collapse text-sm">
                  {children}
                </table>
              </div>
            ),
            thead: ({ children }) => (
              <thead className="border-bg-1 border-b">{children}</thead>
            ),
            tbody: ({ children }) => <tbody>{children}</tbody>,
            tr: ({ children }) => (
              <tr className="border-bg-1 border-b last:border-b-0">
                {children}
              </tr>
            ),
            th: ({ children }) => (
              <th className="text-fg px-3 py-2 text-left font-semibold">
                {children}
              </th>
            ),
            td: ({ children }) => (
              <td className="text-fg-3 px-3 py-2">{children}</td>
            ),
          }}
        >
          {entry.content}
        </ReactMarkdown>
      </div>
    </div>
  )
}

/** Thinking/reasoning entry - collapsible */
export function ThinkingMessage({ entry }: { entry: ThinkingEntry }) {
  const [isExpanded, setIsExpanded] = useState(false)

  return (
    <div className="border-gruvbox-gray border-l-2 pl-3">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="text-fg-4 hover:text-fg-3 flex w-full items-center gap-2 text-left text-xs transition-colors"
      >
        <ChevronIcon expanded={isExpanded} />
        <svg
          className="h-4 w-4"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
          />
        </svg>
        <span>Thinking</span>
        <span className="text-fg-4/60">{formatTime(entry.ts)}</span>
      </button>
      {isExpanded && (
        <div className="bg-bg-1 text-fg-4 mt-2 rounded p-2 text-xs leading-relaxed whitespace-pre-wrap">
          {entry.content}
        </div>
      )}
    </div>
  )
}

/** Tool call entry with status indicator */
export function ToolMessage({ entry }: { entry: ToolEntry }) {
  const [isExpanded, setIsExpanded] = useState(true)

  const statusIcon = {
    running: (
      <div className="border-gruvbox-yellow h-4 w-4 animate-spin rounded-full border-2 border-t-transparent" />
    ),
    success: (
      <svg
        className="text-gruvbox-green h-4 w-4"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M5 13l4 4L19 7"
        />
      </svg>
    ),
    error: (
      <svg
        className="text-gruvbox-red h-4 w-4"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M6 18L18 6M6 6l12 12"
        />
      </svg>
    ),
  }

  const statusColors = {
    running: "border-gruvbox-yellow",
    success: "border-gruvbox-green",
    error: "border-gruvbox-red",
  }

  return (
    <div className={`border-l-2 pl-3 ${statusColors[entry.status]}`}>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="text-fg-4 hover:text-fg-3 flex w-full items-center gap-2 text-left text-xs transition-colors"
      >
        <ChevronIcon expanded={isExpanded} />
        {statusIcon[entry.status]}
        <span className="text-gruvbox-yellow font-mono font-medium">
          {entry.name}
        </span>
        <span className="text-fg-4/60">{formatTime(entry.ts)}</span>
      </button>

      {isExpanded && (
        <div className="mt-2 space-y-2">
          {/* Arguments */}
          {entry.args && (
            <div className="bg-bg-1 rounded p-2">
              <div className="text-fg-4 mb-1 text-[10px] uppercase">Args</div>
              <pre className="text-fg-3 overflow-x-auto text-xs">
                {JSON.stringify(entry.args, null, 2)}
              </pre>
            </div>
          )}

          {/* Result */}
          {entry.result && (
            <div className="bg-bg-1 rounded p-2">
              <div className="text-fg-4 mb-1 text-[10px] uppercase">Result</div>
              <pre className="text-fg-3 max-h-40 overflow-auto text-xs whitespace-pre-wrap">
                {entry.result.length > 1000
                  ? entry.result.slice(0, 1000) + "\n... (truncated)"
                  : entry.result}
              </pre>
            </div>
          )}

          {/* Error */}
          {entry.error && (
            <div className="bg-gruvbox-red/10 rounded p-2">
              <div className="text-gruvbox-red mb-1 text-[10px] uppercase">
                Error
              </div>
              <pre className="text-gruvbox-red text-xs whitespace-pre-wrap">
                {entry.error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// =============================================================================
// Utility Components
// =============================================================================

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={`h-3 w-3 transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M9 5l7 7-7 7"
      />
    </svg>
  )
}
