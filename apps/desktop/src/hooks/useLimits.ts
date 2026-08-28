import { useMemo } from "react";

import { useConnection } from "@/stores/connection";

export interface LimitRow {
  /** The environment variable that sets it, which is also how you change it. */
  name: string;
  value: string;
}

/**
 * The risk limits, under the names that set them.
 *
 * They lived in the left rail beside a gate-family meter. The rail became the
 * committee, and these came here rather than being dropped: the gates tab is where
 * the deterministic half of the system is described, and a gate's live reading —
 * "2/20 open positions" — means little without the 20 beside it.
 *
 * Shown under their environment variable names, with no control beside them. That is
 * the point: a limit changes by editing `.env` and restarting, where the change is a
 * diff someone can review, not by a field in a dashboard that nothing records.
 */
export function useLimits(): LimitRow[] {
  const limits = useConnection((s) => s.snapshot?.limits) ?? {};
  return useMemo(
    () => Object.entries(limits).map(([name, value]) => ({ name, value: String(value) })),
    [limits],
  );
}
