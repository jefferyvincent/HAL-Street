import { useEffect, useState } from "react";
import type { StructureChart } from "@/types";

/**
 * One structure's price history and its exit levels.
 *
 * Its own fetch rather than part of the polled snapshot: the route launches an MCP
 * subprocess and waits on Alpaca, and a chart nobody opened has no business on the
 * critical path of a five-second update.
 *
 * Fetched once per structure and not refreshed. An hourly series does not change
 * mid-look, and a chart that redraws under the cursor while someone is reading it is
 * worse than one that is a few minutes stale.
 */
export function useStructureChart(structureId: string | null) {
  const [chart, setChart] = useState<StructureChart | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!structureId) {
      setChart(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch(`/api/structure/${encodeURIComponent(structureId)}/chart`, { cache: "no-store" })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return (await r.json()) as StructureChart;
      })
      .then((data) => {
        if (cancelled) return;
        setChart(data);
        // A broker outage still returns the structure and its levels, so it is a note
        // on the chart rather than a failure of it.
        setError(data.error ?? null);
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => !cancelled && setLoading(false));

    return () => {
      cancelled = true;
    };
  }, [structureId]);

  return { chart, loading, error };
}
