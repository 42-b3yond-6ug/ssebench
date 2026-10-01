/**
 * Review Content - the reviewer's note on a finished run
 *
 * The note is plain text: shown as it was written, never as markdown or HTML.
 */

export function ReviewContent({ text }: { text: string }) {
  return (
    <div className="bg-bg-hard h-full overflow-y-auto p-4">
      <pre className="text-fg font-sans text-sm leading-relaxed break-words whitespace-pre-wrap">
        {text}
      </pre>
    </div>
  )
}
