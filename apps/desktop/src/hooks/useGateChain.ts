import { useMemo } from "react";
import { byFamily } from "@/lib/gates";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

export interface ChainGate {
  gate: string;
  /** How many proposals this gate has rejected across the whole journal. */
  rejected: number;
  /**
   * What it measured the last time it ran — "2/20 open positions", "1/6 entries this
   * hour". The gate's own sentence, carried through untouched.
   */
  reading: string;
  /** Whether that reading passed. A gate can be near a limit and still clear it. */
  passed: boolean;
}

export interface ChainGroup {
  family: string;
  gates: ChainGate[];
}

export interface GateChain {
  groups: ChainGroup[];
  total: number;
  /** Proposals that reached the chain — the denominator every count is out of. */
  seen: number;
  /** When the readings were taken. Null when the chain has never run. */
  readAt: string | null;
  /** Set when the readings were taken after the close, and said once above them. */
  afterHoursNote: string | null;
  /** What it was reading against. */
  readOf: string;
}

/**
 * The chain as configured, in evaluation order, with how often each gate has actually
 * rejected something and what each one measured the last time it ran.
 *
 * The counts come from the journal and the order comes from the server, so this list
 * cannot drift from what the agent runs — adding a gate changes it on the next push
 * with nothing to update here.
 *
 * The readings are the gates' own sentences, carried through untouched rather than
 * recomputed. A panel that re-derives a limit check is a panel that can disagree with
 * the thing it depicts, and the one place that must never happen is the half of the
 * system that says no.
 */
export function useGateChain(): GateChain {
  const t = useStrings();
  const snap = useConnection((s) => s.snapshot);

  return useMemo(() => {
    if (!snap) {
      return { groups: [], total: 0, seen: 0, readAt: null, readOf: "",
               afterHoursNote: null };
    }
    const by = snap.pnl.rejections_by_gate ?? {};
    const readings = snap.gate_readings ?? {};
    const any = Object.values(readings)[0];
    const stamped = snap.chain.map((c) => ({ ...c, passed: true, reason: "" }));
    return {
      groups: byFamily(stamped, snap.families, snap.chain).map(([family, gs]) => ({
        family,
        gates: gs.map((g) => ({
          gate: g.gate,
          rejected: by[g.gate] ?? 0,
          reading: readings[g.gate]?.reason ?? "",
          passed: readings[g.gate]?.passed ?? true,
        })),
      })),
      total: snap.chain.length,
      // Every gate runs on every proposal — none short-circuits — so one denominator
      // is correct for all of them.
      seen: snap.pnl.approved + snap.pnl.rejected,
      readAt: any?.at ?? null,
      readOf: any?.structure ?? "",
      // Said once, above the list, rather than repeated on seventeen rows. Every
      // reading in a set comes from the same evaluation, so they share an answer.
      afterHoursNote: any?.after_hours ? t.gates.afterHours : null,
    };
  }, [snap, t]);
}
