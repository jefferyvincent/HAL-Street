import { useMemo } from "react";

import { facts, type Fact } from "@/lib/decisions";
import { useFormat } from "@/hooks/useFormat";
import { useStrings } from "@/hooks/useStrings";
import type { Decision } from "@/types";

/** A fact with the words for its own name attached. */
export interface LabelledFact extends Fact {
  label: string;
}

/** The three figures the console shows above the gate ledger, already formatted. */
export function useDecisionFacts(decision: Decision | null): LabelledFact[] {
  const t = useStrings();
  const f = useFormat();

  return useMemo(() => {
    if (!decision) return [];
    return facts(decision, f.money, f.dash).map((fact) => ({
      ...fact,
      label: t.console.facts[fact.key] ?? fact.key,
    }));
  }, [decision, t, f]);
}
