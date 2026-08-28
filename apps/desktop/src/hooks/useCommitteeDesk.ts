import { useMemo } from "react";

import { DESK, deskSeats, type SeatState } from "@/lib/desk";
import { useCommittee, type CommitteeCard } from "@/hooks/useCommittee";
import { useFormat } from "@/hooks/useFormat";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

export interface DeskRow {
  key: string;
  label: string;
  state: SeatState;
  /** Where the seat is, in a word. */
  word: string;
  /** What it said, once it has said anything. */
  text: string | null;
  /** Said about the text rather than by it — that the record bounded it. */
  footnote: string | null;
}

export interface Desk {
  underlying: string;
  /** True while the deliberation is still being had. */
  live: boolean;
  /** The stage in the agent's own words, or how long ago the desk rose. */
  status: string;
  rows: DeskRow[];
  note: string | null;
  /** The words for a panel that has never seen a committee, or null. */
  empty: string | null;
}

/**
 * The desk, live where there is one and from the record where there is not.
 *
 * Which of those it is has to be unmistakable, and it is the whole reason this hook
 * exists rather than the tab reading two sources itself. A finished session and a
 * running one look alike in a list — the tab led with a stack of cards and most of
 * the screen was five and eighteen hours old, with the deliberation actually
 * happening reduced to one word in a header.
 *
 * The seats of a live desk are never filled from the last session. `lib/desk` holds
 * that rule and the test that names it: a real verdict shown against a deliberation
 * that has not reached it yet is worse than an empty row, because a reader cannot
 * tell it apart from one that has.
 */
export function useCommitteeDesk(): Desk {
  const t = useStrings();
  const f = useFormat();
  const cards = useCommittee();
  const flight = useConnection((s) => s.snapshot?.in_flight ?? null);

  return useMemo(() => {
    const done = flight?.done ?? [];
    const live = done.length > 0 && Boolean(flight?.underlying);
    const latest: CommitteeCard | null = cards[0] ?? null;
    const session = latest && {
      catalystAbsent: latest.catalyst.absent !== null || latest.catalyst.lean === null,
      bullAbsent: latest.bull.absent !== null,
      bearAbsent: latest.bear.absent !== null,
      judgeFailed: latest.judge.error !== null,
      passed: latest.verdict.label === t.committee.passed,
      gated: latest.gated !== null,
    };
    const seats = deskSeats({ live: live ? done : null, session });

    const word: Record<SeatState, string> = {
      in: t.committee.desk.in,
      working: t.committee.desk.working,
      pending: t.committee.desk.pending,
      absent: t.committee.desk.absent,
      skipped: t.committee.desk.skipped,
    };

    return {
      underlying: (live ? flight?.underlying : latest?.underlying) ?? "",
      live,
      status: live
        ? (flight?.stage ?? t.committee.desk.live)
        : latest ? t.committee.desk.lastSat(latest.ago) : "",
      rows: seats.map((seat) => ({
        key: seat.key,
        label: t.committee.desk[seat.key],
        state: seat.state,
        word: word[seat.state],
        text: seat.state === "in"
          ? (live ? liveText(seat.key) : said(latest!, seat.key))
          : seat.state === "absent" && !live ? absent(latest!, seat.key)
          : null,
        footnote: !live && latest && clipped(latest, seat.key)
          ? t.committee.desk.clipped : null,
      })),
      note: live ? t.committee.desk.note : null,
      empty: seats.length === 0 ? t.committee.desk.empty : null,
    };

    /** What a live seat can be quoted on, which is the catalyst's read and no more. */
    function liveText(key: string): string | null {
      if (key !== "catalyst") return null;
      if (!flight?.lean) return null;
      return t.committee.desk.read(flight.lean, f.plain(flight.confidence ?? 0, 2));
    }
  }, [cards, flight, t, f]);
}

/** Whether the record kept only the first part of what this seat said. */
function clipped(card: CommitteeCard, key: string): boolean {
  if (key === "bull") return card.bull.clipped;
  if (key === "bear") return card.bear.clipped;
  return false;
}

/** What a seat said, from the finished record. */
function said(card: CommitteeCard, key: string): string | null {
  if (key === "catalyst") return card.catalyst.note || null;
  if (key === "bull") return card.bull.text || null;
  if (key === "bear") return card.bear.text || null;
  if (key === "judge") return card.judge.rationale || null;
  return card.judge.outcome;
}

/** Why a seat is empty. Never the same as having nothing to say. */
function absent(card: CommitteeCard, key: string): string | null {
  if (key === "catalyst") return card.catalyst.absent;
  if (key === "bull") return card.bull.absent;
  if (key === "bear") return card.bear.absent;
  if (key === "judge") return card.judge.error;
  return null;
}

export { DESK };
