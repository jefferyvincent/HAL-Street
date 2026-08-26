import { useMemo } from "react";
import { byFamily } from "@/lib/gates";
import { useConnection } from "@/stores/connection";

export interface ChainGate {
  gate: string;
  /** How many proposals this gate has rejected across the whole journal. */
  rejected: number;
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
}

/**
 * The chain as configured, in evaluation order, with how often each gate has actually
 * rejected something.
 *
 * The counts come from the journal and the order comes from the server, so this list
 * cannot drift from what the agent runs — adding a gate changes it on the next push
 * with nothing to update here.
 */
export function useGateChain(): GateChain {
  const snap = useConnection((s) => s.snapshot);

  return useMemo(() => {
    if (!snap) return { groups: [], total: 0, seen: 0 };
    const by = snap.pnl.rejections_by_gate ?? {};
    const stamped = snap.chain.map((c) => ({ ...c, passed: true, reason: "" }));
    return {
      groups: byFamily(stamped, snap.families, snap.chain).map(([family, gs]) => ({
        family,
        gates: gs.map((g) => ({ gate: g.gate, rejected: by[g.gate] ?? 0 })),
      })),
      total: snap.chain.length,
      // Every gate runs on every proposal — none short-circuits — so one denominator
      // is correct for all of them.
      seen: snap.pnl.approved + snap.pnl.rejected,
    };
  }, [snap]);
}
