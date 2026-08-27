import { useEffect, useState } from "react";
import type { StructureChart } from "@/types";

/**
 * One structure's price history and its exit levels.
 *
 * Its own fetch rather than part of the polled snapshot: the route launches an MCP
 * subprocess and waits on Alpaca, and a chart nobody opened has no business on the
 * critical path of a five-second update.
 *
 * Fetched once per structure, and again when the bar size changes. Not on a timer:
 * an hourly series does not change mid-look, a chart that redraws under the cursor is
 * worse than one a few minutes stale, and the live edge is the forming candle's job.
 */
export function useStructureChart(structureId: string | null,
                                 timeframe: string | null = null) {
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

    const query = timeframe ? `?timeframe=${encodeURIComponent(timeframe)}` : "";
    fetch(`/api/structure/${encodeURIComponent(structureId)}/chart${query}`,
          { cache: "no-store" })
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
  }, [structureId, timeframe]);

  return { chart, loading, error };
}
