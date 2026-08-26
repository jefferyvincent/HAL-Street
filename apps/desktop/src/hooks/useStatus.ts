import { useMemo } from "react";
import { useConnection } from "@/stores/connection";
import type { FamilyGroup } from "./useGateFamilies";
import { useStrings } from "./useStrings";

export interface Status {
  connected: boolean;
  transport: "socket" | "poll" | null;
  error: string | null;
  at: string | null;
  gates: number;
  /** "CONTRACT 2 · LIQUIDITY 2 · …" — the chain's shape, in one line. */
  meter: string;
}

/** Everything the footer says, assembled away from the markup that says it. */
export function useStatus(families: FamilyGroup[]): Status {
  const { connected, transport, error, at, snapshot } = useConnection();
  const t = useStrings();

  const meter = useMemo(
    () =>
      families
        .map((f) => `${(t.families[f.family] ?? f.family).toUpperCase()} ${f.gates.length}`)
        .join(" · ") || "—",
    [families, t],
  );

  return { connected, transport, error, at, gates: snapshot?.chain.length ?? 0, meter };
}
