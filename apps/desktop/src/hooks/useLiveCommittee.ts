import { useMemo } from "react";

import { liveStages, type StageState } from "@/lib/liveSession";
import { useFormat } from "@/hooks/useFormat";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

export interface LiveStageRow {
  key: string;
  label: string;
  state: StageState;
  /** What the stage produced, where it has produced anything yet. */
  detail: string | null;
}

export interface LiveSession {
  underlying: string;
  /** The coarse label, always present while a cycle is running. */
  stage: string;
  title: string;
  note: string;
  /** Empty until the agent has reported a stage — see `lib/liveSession`. */
  rows: LiveStageRow[];
  stateWord: Record<StageState, string>;
}

/**
 * The deliberation happening right now, drawn as it fills in.
 *
 * Null whenever nothing is running, which is most of the time: the agent scans on a
 * cadence and a cycle is about a minute of a half hour. That is the correct answer,
 * not an empty state — the archive below it is what a quiet panel should be showing.
 *
 * The catalyst's read appears on the card the moment it lands, roughly forty seconds
 * before the session it belongs to does. It is shown against the name the agent
 * recorded it under and never inferred: a lean carried over from the previous symbol
 * would be a real read attributed to the wrong company, which is worse than no card.
 */
export function useLiveCommittee(): LiveSession | null {
  const t = useStrings();
  const f = useFormat();
  const flight = useConnection((s) => s.snapshot?.in_flight ?? null);

  return useMemo(() => {
    if (!flight || !flight.underlying) return null;

    const detail = (key: string): string | null => {
      if (key !== "catalyst") return null;
      if (flight.catalyst_error) return t.committee.live.readFailed(flight.catalyst_error);
      if (!flight.lean) return null;
      return t.committee.live.read(flight.lean, f.plain(flight.confidence ?? 0, 2));
    };

    return {
      underlying: flight.underlying,
      stage: flight.stage,
      title: t.committee.live.title,
      note: t.committee.live.note,
      rows: liveStages(flight.done ?? []).map((s) => ({
        key: s.key,
        label: t.committee.live[s.key],
        state: s.state,
        detail: s.state === "done" ? detail(s.key) : null,
      })),
      stateWord: {
        done: t.committee.live.done,
        running: t.committee.live.running,
        pending: t.committee.live.pending,
      },
    };
  }, [flight, t, f]);
}
