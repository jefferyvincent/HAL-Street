import { useEffect, useState } from "react";
import { MARKS_INTERVAL_MS } from "@/constants/theme";
import type { Marks } from "@/types";

/**
 * Live marks for the open book, polled on their own slow cadence.
 *
 * Separate from the socket on purpose. The snapshot is pushed whenever a file
 * changes and reaches no further than disk; this asks the broker, so it is a fetch
 * the panel makes deliberately and rarely rather than something riding on every
 * update.
 *
 * Failure is not an error state. The caller falls back to the agent's own last
 * mark, which the journal already carries and which the panel labels with its age —
 * a stale number that says it is stale beats a blank space that looks like a bug.
 */
export function useMarks(): Marks | null {
  const [marks, setMarks] = useState<Marks | null>(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const response = await fetch("/api/marks");
        if (!response.ok) return;
        const body = (await response.json()) as Marks;
        if (alive) setMarks(body);
      } catch {
        // Offline, or the broker is unreachable. Keep whatever we had.
      }
    };
    void load();
    const timer = window.setInterval(load, MARKS_INTERVAL_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  return marks;
}
