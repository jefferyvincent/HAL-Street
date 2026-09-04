import { useMemo } from "react";

import { liveStages, type StageState } from "@/lib/liveSession";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

export interface LiveStageRow {
  key: string;
  label: string;
  state: StageState;
}

/**
 * The three model calls of a deliberation in progress, in order, for the rail.
 *
 * Null whenever nothing is running, which is most of the time: the agent scans on a
 * cadence and a cycle is about a minute of every thirty. That is the correct answer
 * rather than an empty state — a rail that draws an idle committee is claiming one.
 *
 * The tab's desk is the fuller version of this; see `useCommitteeDesk`.
 */
export function useLiveCommittee(): LiveStageRow[] | null {
  const t = useStrings();
  const flight = useConnection((s) => s.snapshot?.in_flight ?? null);

  return useMemo(() => {
    if (!flight?.underlying) return null;
    const rows = liveStages(flight.done ?? []);
    if (rows.length === 0) return null;
    return rows.map((s) => ({ key: s.key, label: t.committee.desk[s.key], state: s.state }));
  }, [flight, t]);
}
