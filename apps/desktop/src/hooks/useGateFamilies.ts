import { useMemo } from "react";
import { byFamily } from "@/lib/gates";
import { useConnection } from "@/stores/connection";
import type { Decision, GateVerdict } from "@/types";

export interface FamilyGroup {
  family: string;
  gates: GateVerdict[];
  failed: number;
}

/**
 * A decision's verdicts, grouped by the family the gate layer stamped on them.
 *
 * With nothing selected this returns the chain at rest — the gates that *will* run,
 * all marked passed. That is a deliberate placeholder rather than an empty rail: the
 * shape of the chain is worth showing before the first proposal arrives.
 */
export function useGateFamilies(decision: Decision | null): FamilyGroup[] {
  const snap = useConnection((s) => s.snapshot);

  return useMemo(() => {
    if (!snap) return [];
    const gates: GateVerdict[] =
      decision?.gates ?? snap.chain.map((c) => ({ ...c, passed: true, reason: "" }));
    return byFamily(gates, snap.families, snap.chain).map(([family, gs]) => ({
      family,
      gates: gs,
      failed: gs.filter((g) => !g.passed).length,
    }));
  }, [snap, decision]);
}
