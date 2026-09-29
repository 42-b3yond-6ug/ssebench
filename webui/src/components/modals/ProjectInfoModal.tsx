/**
 * Project Info Modal
 *
 * Displays detailed project information including task description, crash reports, and PoC files.
 * Used by ProjectInfoBar to show full details when "More Details" is clicked.
 */

import type { ProjectInfo } from "../../types/container"

interface ProjectInfoModalProps {
  project: ProjectInfo
  isOpen: boolean
  onClose: () => void
}

export function ProjectInfoModal({
  project,
  isOpen,
  onClose,
}: ProjectInfoModalProps) {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="bg-bg/80 absolute inset-0 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="border-border-subtle bg-bg-hard relative z-10 max-h-[80vh] w-full max-w-lg overflow-auto rounded-lg border shadow-xl">
        {/* Header */}
        <div className="border-border-subtle flex items-center justify-between border-b px-4 py-3">
          <h2 className="text-fg text-sm font-medium">Project Info</h2>
          <button
            onClick={onClose}
            className="text-fg-4 hover:bg-bg-1 hover:text-fg rounded p-1 transition-colors"
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
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="space-y-4 p-4">
          {/* Basic info */}
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div>
              <span className="text-fg-4">Task ID:</span>
              <div className="text-gruvbox-yellow font-mono">{project.id}</div>
            </div>
            <div>
              <span className="text-fg-4">Project:</span>
              <div className="text-fg font-mono">{project.project}</div>
            </div>
            <div>
              <span className="text-fg-4">Language:</span>
              <div className="text-gruvbox-aqua font-mono">
                {project.language}
              </div>
            </div>
            <div>
              <span className="text-fg-4">Source:</span>
              <div
                className="text-fg-3 truncate font-mono text-xs"
                title={project.source}
              >
                {project.source}
              </div>
            </div>
          </div>

          {/* Task description */}
          {project.task_description && (
            <div>
              <span className="text-fg-4 text-sm">Task Description:</span>
              <div className="bg-bg-1 mt-1 rounded p-2 text-sm">
                {project.task_description.bug_description ? (
                  <p className="text-fg-3">
                    {project.task_description.bug_description}
                  </p>
                ) : project.task_description.issue ? (
                  <p className="text-fg-3">{project.task_description.issue}</p>
                ) : (
                  <p className="text-fg-4 italic">No description available</p>
                )}
              </div>
            </div>
          )}

          {/* Crash reports */}
          {project.task_description?.crash_report &&
            project.task_description.crash_report.length > 0 && (
              <div>
                <span className="text-fg-4 text-sm">Crash Reports:</span>
                <ul className="text-fg-3 mt-1 space-y-1 font-mono text-xs">
                  {project.task_description.crash_report.map((report, i) => (
                    <li key={i} className="text-gruvbox-orange">
                      {report}
                    </li>
                  ))}
                </ul>
              </div>
            )}

          {/* PoC files */}
          {project.poc && project.poc.length > 0 && (
            <div>
              <span className="text-fg-4 text-sm">PoC Files:</span>
              <ul className="text-fg-3 mt-1 space-y-1 font-mono text-xs">
                {project.poc.map((poc, i) => (
                  <li key={i} className="text-gruvbox-purple">
                    {poc}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
