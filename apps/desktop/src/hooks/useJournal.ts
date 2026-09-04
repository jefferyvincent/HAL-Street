import { useMemo } from "react";

import { useDecisions } from "@/hooks/useDecisions";
import { useFormat } from "@/hooks/useFormat";
import { useStrings } from "@/hooks/useStrings";
import { useUI } from "@/stores/ui";

export interface JournalLine {
  ts: string;
  day: string;
  time: string;
  verdict: string;
  approved: boolean;
  /** Null renders as the dash: no ticker was recorded on this decision. */
  underlying: string | null;
  structure: string;
  /** "11/16" — passed over ran. */
  gates: string;
  /** The gates it failed on, already joined, or null when it failed none. */
  failed: string | null;
  selected: boolean;
}

/**
 * Every decision as the table shows it: one line per record, newest first.
 *
 * The same rows the tape reads, formatted for the width this view has. The tape
 * truncates to one column and this does not, which is the only difference between
 * them — and the reason they share `useDecisions` rather than each walking the
 * journal their own way.
 */
export function useJournal() {
  const t = useStrings();
  const f = useFormat();
  const { rows, selected } = useDecisions();
  const open = useUI((s) => s.showDecision);

  const lines = useMemo<JournalLine[]>(() => rows.map((r) => ({
    ts: r.ts,
    day: f.day(r.ts),
    time: f.clock(r.ts),
    verdict: r.decision.approved ? t.journal.approved : t.journal.rejected,
    approved: r.decision.approved,
    underlying: r.decision.underlying ?? null,
    structure: r.decision.structure ?? t.common.dash,
    gates: t.journal.gateCount(r.passedCount, r.total),
    failed: r.failed.length
      ? r.failed.map((g) => g.gate).join(t.common.listSep)
      : null,
    selected: r.ts === selected,
  })), [rows, selected, t, f]);

  return { lines, open };
}
