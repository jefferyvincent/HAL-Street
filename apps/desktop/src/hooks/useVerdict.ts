import { useMemo } from "react";

import { toRow } from "@/lib/decisions";
import { useStrings } from "@/hooks/useStrings";
import type { Decision, GateVerdict } from "@/types";

export interface Verdict {
  ok: boolean;
  total: number;
  failed: GateVerdict[];
  /** "APPROVED · 16/16 GATES", or the rejection with its count. */
  label: string;
}

/**
 * What the chain did with one decision.
 *
 * The same count the tape and the journal show, from the same `toRow` — three views
 * that each did their own `gates.filter(...)` are three places for the arithmetic of
 * "how many passed" to drift apart.
 */
export function useVerdict(decision: Decision | null): Verdict | null {
  const t = useStrings();

  return useMemo(() => {
    if (!decision) return null;
    const { failed, total } = toRow(decision);
    const ok = decision.approved;
    return {
      ok,
      total,
      failed,
      label: ok ? t.console.approved(total) : t.console.rejected(failed.length, total),
    };
  }, [decision, t]);
}
