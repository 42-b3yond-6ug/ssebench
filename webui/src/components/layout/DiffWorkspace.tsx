/**
 * Diff Workspace - Main center panel
 *
 * Displays unified diff from SDK /diff endpoint.
 * Parses git diff format and renders with syntax highlighting.
 */

import { useState, useMemo } from "react"
import { useSDKDataContext } from "../../context/useSDKDataContext"
import hljs from "highlight.js/lib/core"
import "../../styles/hljs-gruvbox.css"

// Import commonly used languages
import go from "highlight.js/lib/languages/go"
import python from "highlight.js/lib/languages/python"
import javascript from "highlight.js/lib/languages/javascript"
import typescript from "highlight.js/lib/languages/typescript"
import rust from "highlight.js/lib/languages/rust"
import c from "highlight.js/lib/languages/c"
import cpp from "highlight.js/lib/languages/cpp"
import java from "highlight.js/lib/languages/java"
import ruby from "highlight.js/lib/languages/ruby"
import php from "highlight.js/lib/languages/php"
import shell from "highlight.js/lib/languages/shell"
import bash from "highlight.js/lib/languages/bash"
import json from "highlight.js/lib/languages/json"
import yaml from "highlight.js/lib/languages/yaml"
import xml from "highlight.js/lib/languages/xml"
import css from "highlight.js/lib/languages/css"
import sql from "highlight.js/lib/languages/sql"
import markdown from "highlight.js/lib/languages/markdown"

// Register languages
hljs.registerLanguage("go", go)
hljs.registerLanguage("python", python)
hljs.registerLanguage("javascript", javascript)
hljs.registerLanguage("typescript", typescript)
hljs.registerLanguage("rust", rust)
hljs.registerLanguage("c", c)
hljs.registerLanguage("cpp", cpp)
hljs.registerLanguage("java", java)
hljs.registerLanguage("ruby", ruby)
hljs.registerLanguage("php", php)
hljs.registerLanguage("shell", shell)
hljs.registerLanguage("bash", bash)
hljs.registerLanguage("json", json)
hljs.registerLanguage("yaml", yaml)
hljs.registerLanguage("xml", xml)
hljs.registerLanguage("css", css)
hljs.registerLanguage("sql", sql)
hljs.registerLanguage("markdown", markdown)

// Map file extensions to highlight.js language names
const extToLang: Record<string, string> = {
  go: "go",
  py: "python",
  js: "javascript",
  jsx: "javascript",
  ts: "typescript",
  tsx: "typescript",
  rs: "rust",
  c: "c",
  h: "c",
  cpp: "cpp",
  cc: "cpp",
  cxx: "cpp",
  hpp: "cpp",
  java: "java",
  rb: "ruby",
  php: "php",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  json: "json",
  yaml: "yaml",
  yml: "yaml",
  xml: "xml",
  html: "xml",
  htm: "xml",
  css: "css",
  sql: "sql",
  md: "markdown",
}

// Get language from file path
function getLanguage(filePath: string): string | undefined {
  const ext = filePath.split(".").pop()?.toLowerCase()
  return ext ? extToLang[ext] : undefined
}

// Types for parsed diff
interface DiffHunk {
  oldStart: number
  oldCount: number
  newStart: number
  newCount: number
  lines: DiffLine[]
}

interface DiffFile {
  oldPath: string
  newPath: string
  hunks: DiffHunk[]
}

interface DiffLine {
  type: "add" | "remove" | "context"
  content: string
  oldLineNo?: number
  newLineNo?: number
}

// Parse unified diff into structured format
function parseDiff(diffText: string): DiffFile[] {
  if (!diffText.trim()) return []

  const files: DiffFile[] = []
  const lines = diffText.split("\n")
  let currentFile: DiffFile | null = null
  let currentHunk: DiffHunk | null = null
  let oldLineNo = 0
  let newLineNo = 0

  for (const line of lines) {
    // File header: diff --git a/path b/path
    if (line.startsWith("diff --git")) {
      if (currentFile) files.push(currentFile)
      const match = line.match(/diff --git a\/(.*) b\/(.*)/)
      currentFile = {
        oldPath: match?.[1] || "",
        newPath: match?.[2] || "",
        hunks: [],
      }
      currentHunk = null
      continue
    }

    // Skip index line
    if (line.startsWith("index ")) continue

    // Old file path: --- a/path
    if (line.startsWith("--- ")) {
      if (currentFile) {
        const path = line.slice(4)
        if (path !== "/dev/null") {
          currentFile.oldPath = path.startsWith("a/") ? path.slice(2) : path
        }
      }
      continue
    }

    // New file path: +++ b/path
    if (line.startsWith("+++ ")) {
      if (currentFile) {
        const path = line.slice(4)
        if (path !== "/dev/null") {
          currentFile.newPath = path.startsWith("b/") ? path.slice(2) : path
        }
      }
      continue
    }

    // Hunk header: @@ -old,count +new,count @@
    if (line.startsWith("@@")) {
      const match = line.match(/@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@/)
      if (match && currentFile) {
        currentHunk = {
          oldStart: parseInt(match[1]),
          oldCount: parseInt(match[2] || "1"),
          newStart: parseInt(match[3]),
          newCount: parseInt(match[4] || "1"),
          lines: [],
        }
        oldLineNo = currentHunk.oldStart
        newLineNo = currentHunk.newStart
        currentFile.hunks.push(currentHunk)
      }
      continue
    }

    // Diff lines
    if (currentHunk) {
      if (line.startsWith("+")) {
        currentHunk.lines.push({
          type: "add",
          content: line.slice(1),
          newLineNo: newLineNo++,
        })
      } else if (line.startsWith("-")) {
        currentHunk.lines.push({
          type: "remove",
          content: line.slice(1),
          oldLineNo: oldLineNo++,
        })
      } else if (line.startsWith(" ") || line === "") {
        currentHunk.lines.push({
          type: "context",
          content: line.slice(1) || "",
          oldLineNo: oldLineNo++,
          newLineNo: newLineNo++,
        })
      }
    }
  }

  if (currentFile) files.push(currentFile)
  return files
}

// Highlight a single line of code
function highlightLine(content: string, language?: string): string {
  if (!language || !content.trim()) {
    // Escape HTML for non-highlighted content
    return content
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
  }

  try {
    const result = hljs.highlight(content, { language, ignoreIllegals: true })
    return result.value
  } catch {
    // Fallback to escaped content
    return content
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
  }
}

// Diff line component
function DiffLineRow({
  line,
  language,
}: {
  line: DiffLine
  language?: string
}) {
  const styles = {
    add: "bg-diff-add-bg",
    remove: "bg-diff-remove-bg",
    context: "",
  }

  const prefix = {
    add: "+",
    remove: "-",
    context: " ",
  }

  const prefixColors = {
    add: "text-diff-add",
    remove: "text-diff-remove",
    context: "text-fg-4",
  }

  const highlightedContent = useMemo(
    () => highlightLine(line.content, language),
    [line.content, language]
  )

  return (
    <div className={`flex min-w-fit font-mono text-sm ${styles[line.type]}`}>
      <span className="text-fg-4 w-12 flex-shrink-0 px-2 text-right select-none">
        {line.oldLineNo || ""}
      </span>
      <span className="text-fg-4 w-12 flex-shrink-0 px-2 text-right select-none">
        {line.newLineNo || ""}
      </span>
      <span
        className={`w-6 flex-shrink-0 text-center select-none ${prefixColors[line.type]}`}
      >
        {prefix[line.type]}
      </span>
      <span
        className="hljs px-2 whitespace-pre"
        dangerouslySetInnerHTML={{ __html: highlightedContent }}
      />
    </div>
  )
}

// Chevron icon component
function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={`h-4 w-4 transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}
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

// File icon based on extension
function FileIcon({ filename }: { filename: string }) {
  const ext = filename.split(".").pop()?.toLowerCase()

  // Color based on file type
  const colors: Record<string, string> = {
    go: "text-[#00ADD8]",
    py: "text-[#3776AB]",
    js: "text-[#F7DF1E]",
    jsx: "text-[#61DAFB]",
    ts: "text-[#3178C6]",
    tsx: "text-[#61DAFB]",
    rs: "text-[#DEA584]",
    c: "text-[#A8B9CC]",
    cpp: "text-[#00599C]",
    java: "text-[#ED8B00]",
    rb: "text-[#CC342D]",
    php: "text-[#777BB4]",
    json: "text-gruvbox-yellow",
    yaml: "text-gruvbox-purple",
    yml: "text-gruvbox-purple",
    md: "text-fg-3",
  }

  return (
    <svg
      className={`h-4 w-4 flex-shrink-0 ${colors[ext || ""] || "text-fg-4"}`}
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
      />
    </svg>
  )
}

// Stat bar showing additions/deletions ratio
function StatBar({
  additions,
  deletions,
}: {
  additions: number
  deletions: number
}) {
  const total = additions + deletions
  if (total === 0) return null

  const blocks = 5 // Number of blocks to show
  const addBlocks = Math.round((additions / total) * blocks)
  const delBlocks = blocks - addBlocks

  return (
    <div className="flex gap-0.5">
      {Array.from({ length: addBlocks }).map((_, i) => (
        <div key={`add-${i}`} className="bg-gruvbox-green h-2 w-2 rounded-sm" />
      ))}
      {Array.from({ length: delBlocks }).map((_, i) => (
        <div key={`del-${i}`} className="bg-gruvbox-red h-2 w-2 rounded-sm" />
      ))}
    </div>
  )
}

// File diff header - clickable to toggle collapse
function DiffFileHeader({
  file,
  additions,
  deletions,
  isExpanded,
  onToggle,
}: {
  file: DiffFile
  additions: number
  deletions: number
  isExpanded: boolean
  onToggle: () => void
}) {
  const filepath = file.newPath || file.oldPath
  const parts = filepath.split("/")
  const filename = parts.pop() || filepath
  const directory = parts.length > 0 ? parts.join("/") + "/" : ""

  return (
    <button
      onClick={onToggle}
      className="border-border-subtle bg-bg-1 hover:bg-bg-2 flex w-full items-center gap-3 border-b px-4 py-2.5 text-left transition-colors"
    >
      {/* Chevron */}
      <span className="text-fg-4">
        <ChevronIcon expanded={isExpanded} />
      </span>

      {/* File icon */}
      <FileIcon filename={filename} />

      {/* File path */}
      <span className="flex min-w-0 flex-1 items-baseline gap-1 font-mono text-sm">
        {directory && <span className="text-fg-4 truncate">{directory}</span>}
        <span className="text-fg font-medium">{filename}</span>
      </span>

      {/* Stats */}
      <div className="flex items-center gap-3">
        {(additions > 0 || deletions > 0) && (
          <span className="text-fg-4 flex items-center gap-2 text-xs">
            {additions > 0 && (
              <span className="text-gruvbox-green font-medium">
                +{additions}
              </span>
            )}
            {deletions > 0 && (
              <span className="text-gruvbox-red font-medium">-{deletions}</span>
            )}
          </span>
        )}
        <StatBar additions={additions} deletions={deletions} />
      </div>
    </button>
  )
}

// Single file diff card with collapsible content
function DiffFileCard({
  file,
  stats,
  language,
  isExpanded,
  onToggle,
}: {
  file: DiffFile
  stats: { additions: number; deletions: number }
  language?: string
  isExpanded: boolean
  onToggle: () => void
}) {
  return (
    <div className="border-border-subtle bg-bg mb-4 min-w-0 overflow-hidden rounded-lg border">
      <DiffFileHeader
        file={file}
        additions={stats.additions}
        deletions={stats.deletions}
        isExpanded={isExpanded}
        onToggle={onToggle}
      />

      {isExpanded && (
        <div className="bg-bg-hard min-w-0 overflow-x-auto">
          {file.hunks.map((hunk, hunkIdx) => (
            <div key={hunkIdx}>
              {/* Hunk header */}
              <div className="bg-bg-1/50 text-fg-4 border-border-subtle border-b px-4 py-1 font-mono text-xs">
                @@ -{hunk.oldStart},{hunk.oldCount} +{hunk.newStart},
                {hunk.newCount} @@
              </div>
              {/* Hunk lines */}
              <div className="min-w-fit">
                {hunk.lines.map((line, lineIdx) => (
                  <DiffLineRow key={lineIdx} line={line} language={language} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// Empty state
function EmptyState() {
  return (
    <div className="text-fg-4 flex h-full flex-col items-center justify-center">
      <div className="mb-4 text-6xl opacity-20"></div>
      <h3 className="text-fg-3 mb-2 text-lg font-medium">No changes yet</h3>
      <p className="max-w-md text-center text-sm">
        When the agent modifies files, the diff will appear here.
      </p>
    </div>
  )
}

// Loading state
function LoadingState() {
  return (
    <div className="text-fg-4 flex h-full flex-col items-center justify-center">
      <div className="border-gruvbox-aqua mb-4 h-8 w-8 animate-spin rounded-full border-2 border-t-transparent" />
      <span className="text-sm">Loading diff...</span>
    </div>
  )
}

// Initializing state - shown while waiting for SDK to become available
function InitializingState({ retryAttempt }: { retryAttempt: number }) {
  return (
    <div className="text-fg-4 flex h-full flex-col items-center justify-center">
      <div className="border-gruvbox-aqua mb-4 h-8 w-8 animate-spin rounded-full border-2 border-t-transparent" />
      <span className="text-sm">Initializing SDK...</span>
      {retryAttempt > 2 && (
        <span className="text-fg-4 mt-2 text-xs opacity-60">
          This may take a moment...
        </span>
      )}
    </div>
  )
}

// Error state
function ErrorState({ message }: { message: string }) {
  return (
    <div className="text-fg-4 flex h-full flex-col items-center justify-center">
      <div className="text-gruvbox-red mb-2 text-lg">Failed to load diff</div>
      <div className="text-sm opacity-60">{message}</div>
    </div>
  )
}

// Refresh button
function RefreshButton({
  onClick,
  isRefreshing,
}: {
  onClick: () => void
  isRefreshing: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={isRefreshing}
      className="text-fg-4 hover:bg-bg-1 hover:text-fg rounded p-1 transition-colors disabled:opacity-50"
      title="Refresh diff"
    >
      <svg
        className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
        />
      </svg>
    </button>
  )
}

// Expand/Collapse all buttons
function ExpandCollapseButtons({
  onExpandAll,
  onCollapseAll,
  allExpanded,
  allCollapsed,
}: {
  onExpandAll: () => void
  onCollapseAll: () => void
  allExpanded: boolean
  allCollapsed: boolean
}) {
  return (
    <div className="flex items-center gap-1">
      <button
        onClick={onExpandAll}
        disabled={allExpanded}
        className="text-fg-4 hover:bg-bg-1 hover:text-fg rounded px-2 py-1 text-xs transition-colors disabled:opacity-30"
        title="Expand all files"
      >
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
            d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"
          />
        </svg>
      </button>
      <button
        onClick={onCollapseAll}
        disabled={allCollapsed}
        className="text-fg-4 hover:bg-bg-1 hover:text-fg rounded px-2 py-1 text-xs transition-colors disabled:opacity-30"
        title="Collapse all files"
      >
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
            d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25"
          />
        </svg>
      </button>
    </div>
  )
}

// View mode toggle button
function ViewModeToggle({
  isRawView,
  onToggle,
}: {
  isRawView: boolean
  onToggle: () => void
}) {
  return (
    <button
      onClick={onToggle}
      className="border-border-subtle text-fg-4 hover:text-fg flex items-center gap-1.5 rounded border px-2 py-1 text-xs transition-colors"
      title={isRawView ? "Switch to parsed view" : "Switch to raw view"}
    >
      {isRawView ? (
        <>
          <svg
            className="h-3.5 w-3.5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 6h16M4 10h16M4 14h16M4 18h16"
            />
          </svg>
          <span>Parsed</span>
        </>
      ) : (
        <>
          <svg
            className="h-3.5 w-3.5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"
            />
          </svg>
          <span>Raw</span>
        </>
      )}
    </button>
  )
}

// Raw diff view component
function RawDiffView({
  diff,
  onExport,
}: {
  diff: string
  onExport: () => void
}) {
  return (
    <div className="relative flex h-full flex-col">
      {/* Raw diff content */}
      <div className="flex-1 overflow-auto p-4">
        <pre className="bg-bg-hard border-border-subtle text-fg-3 rounded-lg border p-4 font-mono text-sm break-all whitespace-pre-wrap">
          {diff || "No changes"}
        </pre>
      </div>

      {/* Export button - fixed at bottom right */}
      {diff && (
        <div className="absolute right-6 bottom-6">
          <button
            onClick={onExport}
            className="bg-gruvbox-aqua hover:bg-gruvbox-aqua/80 text-bg-hard flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium shadow-lg transition-colors"
          >
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
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
              />
            </svg>
            Export Diff
          </button>
        </div>
      )}
    </div>
  )
}

// Single diff pane for split view
function DiffPane({
  title,
  titleColor,
  files,
  getFileStats,
  getLanguage,
  emptyMessage,
}: {
  title: string
  titleColor: string
  files: DiffFile[]
  getFileStats: (file: DiffFile) => { additions: number; deletions: number }
  getLanguage: (filePath: string) => string | undefined
  emptyMessage: string
}) {
  const [expandedFiles, setExpandedFiles] = useState<Set<number>>(
    () => new Set(files.map((_, i) => i))
  )

  const toggleFile = (index: number) => {
    setExpandedFiles((prev) => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  // Calculate total stats
  const totalStats = useMemo(() => {
    let additions = 0
    let deletions = 0
    for (const file of files) {
      const stats = getFileStats(file)
      additions += stats.additions
      deletions += stats.deletions
    }
    return { additions, deletions }
  }, [files, getFileStats])

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      {/* Pane header */}
      <div
        className={`border-border-subtle flex h-10 items-center justify-between border-b px-3 ${titleColor}`}
      >
        <span className="text-sm font-medium">{title}</span>
        {files.length > 0 && (
          <span className="text-xs opacity-70">
            {files.length} {files.length === 1 ? "file" : "files"}
            {totalStats.additions > 0 && (
              <span className="text-gruvbox-green ml-2">
                +{totalStats.additions}
              </span>
            )}
            {totalStats.deletions > 0 && (
              <span className="text-gruvbox-red ml-1">
                -{totalStats.deletions}
              </span>
            )}
          </span>
        )}
      </div>

      {/* Pane content */}
      <div className="flex-1 overflow-auto p-3">
        {files.length === 0 ? (
          <div className="text-fg-4 flex h-full items-center justify-center text-sm">
            {emptyMessage}
          </div>
        ) : (
          <div className="flex flex-col">
            {files.map((file, fileIdx) => {
              const stats = getFileStats(file)
              const language = getLanguage(file.newPath || file.oldPath)
              return (
                <DiffFileCard
                  key={fileIdx}
                  file={file}
                  stats={stats}
                  language={language}
                  isExpanded={expandedFiles.has(fileIdx)}
                  onToggle={() => toggleFile(fileIdx)}
                />
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// Split view showing agent and ground truth side by side
function SplitDiffView({
  agentFiles,
  truthFiles,
  getFileStats,
  getLanguage,
}: {
  agentFiles: DiffFile[]
  truthFiles: DiffFile[]
  getFileStats: (file: DiffFile) => { additions: number; deletions: number }
  getLanguage: (filePath: string) => string | undefined
}) {
  return (
    <div className="flex h-full">
      {/* Agent pane (left) */}
      <DiffPane
        title="Agent Patch"
        titleColor="bg-gruvbox-aqua/10 text-gruvbox-aqua"
        files={agentFiles}
        getFileStats={getFileStats}
        getLanguage={getLanguage}
        emptyMessage="No changes from agent"
      />

      {/* Divider */}
      <div className="bg-border-subtle w-px flex-shrink-0" />

      {/* Ground truth pane (right) */}
      <DiffPane
        title="Ground Truth"
        titleColor="bg-gruvbox-purple/10 text-gruvbox-purple"
        files={truthFiles}
        getFileStats={getFileStats}
        getLanguage={getLanguage}
        emptyMessage="No ground truth available"
      />
    </div>
  )
}

// Patch view toggle component
function PatchViewToggle({
  view,
  onViewChange,
  similarityScore,
}: {
  view: "agent" | "truth" | "split"
  onViewChange: (view: "agent" | "truth" | "split") => void
  similarityScore: number | null
}) {
  return (
    <div className="flex items-center gap-2">
      {/* Similarity indicator */}
      {similarityScore !== null && (
        <div
          className="flex items-center gap-1.5"
          title="How similar the agent's patch is to the ground truth"
        >
          <span className="text-fg-4 text-xs">Similarity:</span>
          {similarityScore >= 80 ? (
            <>
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
                  d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <span className="text-gruvbox-green text-xs font-medium">
                {similarityScore}%
              </span>
            </>
          ) : similarityScore >= 40 ? (
            <>
              <svg
                className="text-gruvbox-yellow h-4 w-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
              <span className="text-gruvbox-yellow text-xs font-medium">
                {similarityScore}%
              </span>
            </>
          ) : (
            <>
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
                  d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <span className="text-gruvbox-red text-xs font-medium">
                {similarityScore}%
              </span>
            </>
          )}
        </div>
      )}

      {/* View toggle buttons */}
      <div className="border-border-subtle flex overflow-hidden rounded-md border">
        <button
          onClick={() => onViewChange("agent")}
          className={`px-2.5 py-1 text-xs font-medium transition-colors ${
            view === "agent"
              ? "bg-gruvbox-aqua text-bg-hard"
              : "text-fg-4 hover:bg-bg-1 hover:text-fg"
          }`}
        >
          Agent
        </button>
        <button
          onClick={() => onViewChange("truth")}
          className={`border-border-subtle border-l px-2.5 py-1 text-xs font-medium transition-colors ${
            view === "truth"
              ? "bg-gruvbox-purple text-bg-hard"
              : "text-fg-4 hover:bg-bg-1 hover:text-fg"
          }`}
        >
          Truth
        </button>
        <button
          onClick={() => onViewChange("split")}
          className={`border-border-subtle border-l px-2.5 py-1 text-xs font-medium transition-colors ${
            view === "split"
              ? "bg-gruvbox-orange text-bg-hard"
              : "text-fg-4 hover:bg-bg-1 hover:text-fg"
          }`}
        >
          Split
        </button>
      </div>
    </div>
  )
}

// Calculate similarity between two diffs using line-based comparison
function calculateDiffSimilarity(
  agentDiff: string,
  truthDiff: string
): number | null {
  if (!agentDiff.trim() || !truthDiff.trim()) return null

  // Extract change lines (+ and -) from both diffs, excluding diff headers
  const extractChangeLines = (diff: string): Set<string> => {
    const lines = new Set<string>()
    for (const line of diff.split("\n")) {
      // Skip diff metadata lines
      if (
        line.startsWith("diff ") ||
        line.startsWith("index ") ||
        line.startsWith("--- ") ||
        line.startsWith("+++ ") ||
        line.startsWith("@@ ")
      ) {
        continue
      }
      // Include actual change lines (normalize whitespace)
      if (line.startsWith("+") || line.startsWith("-")) {
        lines.add(line.trim())
      }
    }
    return lines
  }

  const agentLines = extractChangeLines(agentDiff)
  const truthLines = extractChangeLines(truthDiff)

  if (truthLines.size === 0) return null

  // Calculate intersection
  let matchingLines = 0
  for (const line of agentLines) {
    if (truthLines.has(line)) {
      matchingLines++
    }
  }

  // Calculate Jaccard similarity (intersection / union)
  const unionSize = new Set([...agentLines, ...truthLines]).size
  if (unionSize === 0) return null

  const similarity = (matchingLines / unionSize) * 100
  return Math.round(similarity)
}

export function DiffWorkspace() {
  const [expandedFiles, setExpandedFiles] = useState<Set<number>>(new Set())
  const [isRawView, setIsRawView] = useState(false)
  const [patchView, setPatchView] = useState<"agent" | "truth" | "split">(
    "agent"
  )
  const {
    diff,
    isLoading,
    error,
    refresh,
    isRefreshing,
    isInitializing,
    retryAttempt,
    groundTruthPatch,
  } = useSDKDataContext()

  // Parse the diffs
  const parsedFiles = useMemo(() => parseDiff(diff), [diff])
  const parsedGroundTruth = useMemo(
    () => (groundTruthPatch ? parseDiff(groundTruthPatch) : []),
    [groundTruthPatch]
  )

  // Calculate similarity score
  const similarityScore = useMemo(
    () =>
      groundTruthPatch ? calculateDiffSimilarity(diff, groundTruthPatch) : null,
    [diff, groundTruthPatch]
  )

  // Determine which files to display based on view mode
  const displayFiles = patchView === "truth" ? parsedGroundTruth : parsedFiles
  const displayDiff = patchView === "truth" ? groundTruthPatch || "" : diff

  // Initialize all files as expanded when the view or its file count changes
  const expandKey = `${patchView}:${displayFiles.length}`
  const [expandedForKey, setExpandedForKey] = useState<string | null>(null)
  if (expandedForKey !== expandKey) {
    setExpandedForKey(expandKey)
    if (displayFiles.length > 0) {
      setExpandedFiles(new Set(displayFiles.map((_, i) => i)))
    }
  }

  // Export diff as patch file
  const exportDiff = () => {
    const blob = new Blob([diff], { type: "text/plain" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "patch.diff"
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  // Calculate stats per file
  const getFileStats = (file: DiffFile) => {
    let additions = 0
    let deletions = 0
    for (const hunk of file.hunks) {
      for (const line of hunk.lines) {
        if (line.type === "add") additions++
        if (line.type === "remove") deletions++
      }
    }
    return { additions, deletions }
  }

  // Toggle single file
  const toggleFile = (index: number) => {
    setExpandedFiles((prev) => {
      const next = new Set(prev)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  // Expand/collapse all
  const expandAll = () => {
    setExpandedFiles(new Set(displayFiles.map((_, i) => i)))
  }

  const collapseAll = () => {
    setExpandedFiles(new Set())
  }

  const allExpanded = expandedFiles.size === displayFiles.length
  const allCollapsed = expandedFiles.size === 0

  // Calculate total stats for currently displayed files
  const totalStats = useMemo(() => {
    let additions = 0
    let deletions = 0
    for (const file of displayFiles) {
      const stats = getFileStats(file)
      additions += stats.additions
      deletions += stats.deletions
    }
    return { additions, deletions }
  }, [displayFiles])

  return (
    <main className="bg-bg flex min-h-0 min-w-0 flex-1 flex-col">
      {/* Header */}
      <header className="border-border-subtle flex h-12 items-center justify-between border-b px-4">
        <div className="flex items-center gap-3">
          <h2 className="text-fg text-sm font-medium">Changes</h2>
          {displayFiles.length > 0 && patchView !== "split" && (
            <span className="text-fg-4 text-xs">
              {displayFiles.length}{" "}
              {displayFiles.length === 1 ? "file" : "files"}
              {totalStats.additions > 0 && (
                <span className="text-gruvbox-green ml-2">
                  +{totalStats.additions}
                </span>
              )}
              {totalStats.deletions > 0 && (
                <span className="text-gruvbox-red ml-1">
                  -{totalStats.deletions}
                </span>
              )}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {groundTruthPatch && (
            <PatchViewToggle
              view={patchView}
              onViewChange={setPatchView}
              similarityScore={similarityScore}
            />
          )}
          {displayFiles.length > 0 && patchView !== "split" && (
            <>
              <ViewModeToggle
                isRawView={isRawView}
                onToggle={() => setIsRawView(!isRawView)}
              />
              {!isRawView && (
                <ExpandCollapseButtons
                  onExpandAll={expandAll}
                  onCollapseAll={collapseAll}
                  allExpanded={allExpanded}
                  allCollapsed={allCollapsed}
                />
              )}
            </>
          )}
          <RefreshButton onClick={refresh} isRefreshing={isRefreshing} />
        </div>
      </header>

      {/* Content */}
      <div className="min-h-0 flex-1 overflow-hidden">
        {isInitializing ? (
          <div className="flex h-full items-center justify-center">
            <InitializingState retryAttempt={retryAttempt} />
          </div>
        ) : isLoading ? (
          <div className="flex h-full items-center justify-center">
            <LoadingState />
          </div>
        ) : error ? (
          <div className="flex h-full items-center justify-center">
            <ErrorState message={error} />
          </div>
        ) : patchView === "split" ? (
          <SplitDiffView
            agentFiles={parsedFiles}
            truthFiles={parsedGroundTruth}
            getFileStats={getFileStats}
            getLanguage={getLanguage}
          />
        ) : displayFiles.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <EmptyState />
          </div>
        ) : isRawView ? (
          <RawDiffView diff={displayDiff} onExport={exportDiff} />
        ) : (
          <div className="h-full overflow-auto p-4">
            {/* Ground truth banner */}
            {patchView === "truth" && (
              <div className="bg-gruvbox-purple/20 border-gruvbox-purple/50 text-gruvbox-purple mb-4 flex items-center gap-2 rounded-lg border px-4 py-2 text-sm">
                <svg
                  className="h-4 w-4 flex-shrink-0"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <span>
                  Viewing <strong>ground truth patch</strong> - this is the
                  expected solution from the benchmark
                </span>
              </div>
            )}
            <div className="flex min-w-0 flex-col">
              {displayFiles.map((file, fileIdx) => {
                const stats = getFileStats(file)
                const language = getLanguage(file.newPath || file.oldPath)
                return (
                  <DiffFileCard
                    key={fileIdx}
                    file={file}
                    stats={stats}
                    language={language}
                    isExpanded={expandedFiles.has(fileIdx)}
                    onToggle={() => toggleFile(fileIdx)}
                  />
                )
              })}
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
