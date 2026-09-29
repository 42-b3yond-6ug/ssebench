/**
 * ReasoningBlock - Display AI reasoning/thinking process
 *
 * Shows the AI's thinking process with markdown support.
 * Always visible (not collapsed), styled less prominently than regular messages.
 */

import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import type { ReasoningContent } from "../../types/opencode"

interface ReasoningBlockProps {
  reasoning: ReasoningContent
}

export function ReasoningBlock({ reasoning }: ReasoningBlockProps) {
  const isComplete = !!reasoning.endTime

  return (
    <div className="border-gruvbox-gray/50 bg-bg-1/50 my-2 rounded border-l-2 py-2 pl-3">
      {/* Header */}
      <div className="text-fg-4 mb-1.5 flex items-center gap-2 text-xs">
        <svg
          className="h-3.5 w-3.5 opacity-70"
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
        <span className="font-medium">Thinking</span>
        {!isComplete && (
          <span className="bg-gruvbox-gray/30 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px]">
            <span className="bg-gruvbox-gray inline-block h-1 w-1 animate-pulse rounded-full" />
            reasoning...
          </span>
        )}
      </div>

      {/* Content with markdown */}
      <div className="text-fg-4 prose-invert prose-sm max-w-none text-sm leading-relaxed opacity-80">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            // Style code blocks - more subdued
            code: ({ className, children, ...props }) => {
              const isInline = !className
              if (isInline) {
                return (
                  <code
                    className="bg-bg-2 text-fg-3 rounded px-1 py-0.5 font-mono text-xs"
                    {...props}
                  >
                    {children}
                  </code>
                )
              }
              return (
                <code
                  className="bg-bg-2 block overflow-x-auto rounded p-2 font-mono text-xs"
                  {...props}
                >
                  {children}
                </code>
              )
            },
            // Style pre blocks
            pre: ({ children }) => (
              <pre className="bg-bg-2 my-1.5 overflow-x-auto rounded">
                {children}
              </pre>
            ),
            // Style paragraphs
            p: ({ children }) => (
              <p className="text-fg-4 mb-1.5 last:mb-0">{children}</p>
            ),
            // Style links
            a: ({ href, children }) => (
              <a
                href={href}
                className="text-gruvbox-aqua/70 hover:underline"
                target="_blank"
                rel="noopener noreferrer"
              >
                {children}
              </a>
            ),
            // Style lists
            ul: ({ children }) => (
              <ul className="mb-1.5 list-inside list-disc space-y-0.5 pl-2">
                {children}
              </ul>
            ),
            ol: ({ children }) => (
              <ol className="mb-1.5 list-inside list-decimal space-y-0.5 pl-2">
                {children}
              </ol>
            ),
            li: ({ children }) => <li className="text-fg-4">{children}</li>,
            // Style headings - smaller for reasoning
            h1: ({ children }) => (
              <h1 className="text-fg-3 mb-1.5 text-sm font-semibold">
                {children}
              </h1>
            ),
            h2: ({ children }) => (
              <h2 className="text-fg-3 mb-1.5 text-sm font-semibold">
                {children}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-fg-3 mb-1 text-xs font-semibold">
                {children}
              </h3>
            ),
            // Style blockquotes
            blockquote: ({ children }) => (
              <blockquote className="border-gruvbox-gray/50 text-fg-4 my-1.5 border-l-2 pl-2 text-xs italic opacity-70">
                {children}
              </blockquote>
            ),
            // Style strong/emphasis
            strong: ({ children }) => (
              <strong className="text-fg-3 font-medium">{children}</strong>
            ),
            em: ({ children }) => (
              <em className="text-fg-4 italic">{children}</em>
            ),
            // Style tables (minimal borders, subdued for reasoning)
            table: ({ children }) => (
              <div className="my-1.5 overflow-x-auto">
                <table className="min-w-full border-collapse text-xs">
                  {children}
                </table>
              </div>
            ),
            thead: ({ children }) => (
              <thead className="border-bg-2 border-b">{children}</thead>
            ),
            tbody: ({ children }) => <tbody>{children}</tbody>,
            tr: ({ children }) => (
              <tr className="border-bg-2 border-b last:border-b-0">
                {children}
              </tr>
            ),
            th: ({ children }) => (
              <th className="text-fg-3 px-2 py-1.5 text-left font-medium">
                {children}
              </th>
            ),
            td: ({ children }) => (
              <td className="text-fg-4 px-2 py-1.5">{children}</td>
            ),
          }}
        >
          {reasoning.text}
        </ReactMarkdown>
      </div>
    </div>
  )
}

/**
 * List of reasoning blocks for a message
 */
interface ReasoningListProps {
  reasonings: ReasoningContent[]
}

export function ReasoningList({ reasonings }: ReasoningListProps) {
  if (reasonings.length === 0) return null

  return (
    <div className="space-y-1">
      {reasonings.map((reasoning) => (
        <ReasoningBlock key={reasoning.id} reasoning={reasoning} />
      ))}
    </div>
  )
}
