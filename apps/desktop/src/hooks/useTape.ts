import { useMemo } from "react";

import { useDecisions } from "@/hooks/useDecisions";
import { useFormat } from "@/hooks/useFormat";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";
import { useUI } from "@/stores/ui";

export interface TapeLine {
  ts: string;
  time: string;
  approved: boolean;
  verdict: string;
  /** A rehearsal gated and journalled exactly as a live cycle does. Said on the row. */
  dryRun: boolean;
  structure: string;
  /** The gates it failed on, joined to one line — this column truncates. */
  failed: string;
  underlying: string | null;
  /** The position the decision became, when it became one. */
  structureId: string | null;
  selected: boolean;
}

/**
 * The run as it happened, newest first.
 *
 * Reads the journal itself rather than being handed it: every view that shows
 * decisions goes through `useDecisions`, so "which one is on screen" is answered in
 * one place rather than passed down a prop chain that can go stale.
 */
export function useTape() {
  const t = useStrings();
  const f = useFormat();
  const { rows, selected } = useDecisions();
  const snap = useConnection((s) => s.snapshot);
  const show = useUI((s) => s.showDecision);
  const chart = useUI((s) => s.chart);

  const lines = useMemo<TapeLine[]>(() => rows.map((r) => ({
    ts: r.ts,
    time: f.clock(r.ts),
    approved: r.decision.approved,
    verdict: r.decision.approved
      ? t.tape.approved(r.total)
      : t.tape.rejected(r.failed.length, r.total),
    dryRun: Boolean(r.decision.dry_run),
    structure: r.decision.structure ?? t.common.dash,
    failed: r.failed.map((g) => g.gate).join(t.common.gateSep),
    underlying: r.decision.underlying ?? null,
    structureId: r.decision.structure_id ?? null,
    selected: r.ts === selected,
  })), [rows, selected, t, f]);

  return {
    lines,
    show,
    chart,
    // Nothing at all until the first push: the counts below the title come off the
    // snapshot, and a header with blanks under it reads as a broken panel.
    counts: snap ? t.tape.counts(snap.pnl.approved, snap.pnl.rejected, snap.pnl.passed) : null,
  };
}
