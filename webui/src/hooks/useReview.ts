/**
 * Reviewer's note of a run, if whoever reviewed it left one.
 */

import { useEffect, useState } from "react"
import { fetchReview } from "../lib/api"

/**
 * The note on the run `containerId`, or null while it loads or when there is
 * none. It is asked for once per run: the note is written after the run, by a
 * person, so nothing here changes while the run is open.
 */
export function useReview(containerId: string | null): string | null {
  const [loaded, setLoaded] = useState<{
    id: string
    text: string | null
  } | null>(null)

  useEffect(() => {
    if (!containerId) return
    let cancelled = false
    fetchReview(containerId)
      .then((review) => {
        if (!cancelled) {
          setLoaded({
            id: containerId,
            text: review.available ? review.text : null,
          })
        }
      })
      .catch(() => {
        if (!cancelled) setLoaded({ id: containerId, text: null })
      })
    return () => {
      cancelled = true
    }
  }, [containerId])

  return loaded?.id === containerId ? loaded.text : null
}
