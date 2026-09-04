import { useMemo } from "react";

import { pipeline, type StepState } from "@/lib/pipeline";
import { useFormat } from "@/hooks/useFormat";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

export interface PassStep {
  key: string;
  label: string;
  state: StepState;
}

export interface PassLine {
  key: string;
  underlying: string;
  spot: string | null;
  outcome: string;
  outcomeTone: string;
  running: boolean;
  steps: PassStep[];
  /** What came of it in a few words, or null where the row has nothing to add. */
  detail: string | null;
  /**
   * What the desk believed about this name before it ranked anything: the direction,
   * the volatility regime, and whether direction here tends to continue. Null until a
   * cycle has recorded a view for it.
   */
  read: { text: string; reach: string | null } | null;
}

export interface AgentPass {
  title: string;
  meta: string;
  started: string | null;
  rows: PassLine[];
  empty: string | null;
}

/**
 * The scan the agent is on, name by name.
 *
 * Scan order rather than outcome order — it is a queue being worked through, and
 * re-sorting it would lose the one thing the table is for: seeing where the agent has
 * got to. `_pass` on the server decides what happened to each name; `lib/pipeline`
 * turns that into a track; this puts words on it.
 */
export function useAgentPass(): AgentPass {
  const t = useStrings();
  const f = useFormat();
  const pass = useConnection((s) => s.snapshot?.pass ?? null);
  const views = useConnection((s) => s.snapshot?.views) ?? [];

  return useMemo(() => {
    const rows = pass?.rows ?? [];
    const settled = rows.filter((r) => !r.running).length;

    return {
      title: t.agent.title,
      meta: t.agent.meta(settled, rows.length),
      started: pass ? t.agent.started(f.ago(pass.at)) : null,
      empty: rows.length === 0 ? t.agent.empty : null,
      rows: rows.map((row) => ({
        key: `${row.underlying}@${row.at}`,
        underlying: row.underlying,
        spot: row.spot ? t.agent.spot(row.spot) : null,
        // An outcome this build has never heard of shows as its raw key rather than
        // blank: an empty cell reads as a row that has not got there yet, which is
        // the one distinction this table exists to draw.
        outcome: t.agent.outcome[row.outcome] ?? row.outcome,
        outcomeTone: tone(row.outcome),
        running: row.running,
        steps: pipeline(row).map((s) => ({
          key: s.key, label: t.agent.step[s.key] ?? s.key, state: s.state,
        })),
        read: readFor(row.underlying),
        detail: row.error
          ?? (row.rejected_by.length
                ? t.agent.rejectedBy(row.rejected_by.join(t.common.listSep))
                : row.menu === 0 ? t.agent.menuNone
                : row.menu !== null ? t.agent.menuBuilt(row.menu)
                : null),
      })),
    };

    /** The three reads the cycle took on this name, in one line. */
    function readFor(underlying: string): { text: string; reach: string | null } | null {
      const view = views.find((v) => v.underlying === underlying);
      if (!view?.bias) return null;
      const chain = view.persistence;
      return {
        text: t.agent.read(view.bias, view.regime ?? "", chain?.label ?? t.agent.noRead),
        // How far the chain reaches, said separately from what it found. A read
        // informative for two days is not an argument about a 49-day structure, and
        // printing the label without the horizon would let it be used as one.
        reach: chain ? t.agent.reach(chain.informative_for_days) : null,
      };
    }
  }, [pass, views, t, f]);
}

/** Green for money placed, red for refused or broken, amber for live, grey for quiet. */
function tone(outcome: string): string {
  if (outcome === "submitted") return "text-pass";
  if (outcome === "rejected" || outcome === "error") return "text-fail";
  if (outcome === "running") return "text-amber";
  if (outcome === "approved") return "text-pass/70";
  return "text-ink/40";
}
