import { useMemo } from "react";
import { facts, type Fact } from "@/lib/decisions";
import { money } from "@/lib/format";
import type { Decision } from "@/types";

/** The three figures the console shows above the gate ledger, already formatted. */
export function useDecisionFacts(decision: Decision | null): Fact[] {
  return useMemo(() => (decision ? facts(decision, money) : []), [decision]);
}
