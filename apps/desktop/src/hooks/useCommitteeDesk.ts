import { useMemo } from "react";

import { DESK, deskProgress, deskSeats, type SeatState } from "@/lib/desk";
import { running } from "@/lib/stamp";
import { useCommittee } from "@/hooks/useCommittee";
import { useFormat } from "@/hooks/useFormat";
import { usePresence } from "@/hooks/usePresence";
import { useStrings } from "@/hooks/useStrings";
import { useTick } from "@/hooks/useTick";
import { useConnection } from "@/stores/connection";

export interface DeskRow {
  key: string;
  label: string;
  state: SeatState;
  /** Where the seat is, in a word. */
  word: string;
  /** What it said, once it has said anything. */
  text: string | null;
}

export interface DeskIdle {
  title: string;
  detail: string;
  tone: string;
}

export interface Desk {
  /** True only while a deliberation is actually being had. */
  sitting: boolean;
  underlying: string;
  /** The stage in the agent's own words. */
  stage: string;
  /** 0..1 across the five seats, for the bar. */
  progress: number;
  /** "62% · 0:41", moving. Null before a stage has reported a start. */
  clock: string | null;
  rows: DeskRow[];
  note: string;
  /** Why there is no desk, when there is none. */
  idle: DeskIdle | null;
  /** How many finished sessions are filed behind it. */
  archived: string;
}

/**
 * The desk, and only while it is sitting.
 *
 * It used to fall back to the last finished session, which was the whole complaint:
 * a deliberation that ended five hours ago drawn in the present tense, as the lead
 * item, on the tab whose job is to say what is happening now. Finished sessions are
 * archive; the archive is one control away and holds every one of them.
 *
 * What replaces the fallback is not an empty state but a reason. Four of them, in the
 * order `lib/presence` establishes — a dropped socket outranks a shut market, which
 * outranks a silent agent — because "nothing is happening" covers a panel that cannot
 * be trusted, a market that is closed, and a process that has died, and those call for
 * opposite reactions.
 */
export function useCommitteeDesk(): Desk {
  const t = useStrings();
  const f = useFormat();
  const cards = useCommittee();
  const { kind } = usePresence();
  const flight = useConnection((s) => s.snapshot?.in_flight ?? null);

  const done = flight?.done ?? [];
  const sitting = done.length > 0 && Boolean(flight?.underlying);
  // Only while it is sitting: an idle console redrawing four times a second for a
  // number nobody is reading is a laptop fan.
  const now = useTick(sitting);

  return useMemo(() => {
    const seats = sitting ? deskSeats({ live: done, session: null }) : [];
    const word: Record<SeatState, string> = {
      in: t.committee.desk.in,
      working: t.committee.desk.working,
      pending: t.committee.desk.pending,
      absent: t.committee.desk.absent,
      skipped: t.committee.desk.skipped,
    };
    const progress = deskProgress(seats);
    const since = running(flight?.since, now);

    return {
      sitting,
      underlying: sitting ? (flight?.underlying ?? "") : "",
      stage: flight?.stage ?? "",
      progress,
      clock: since
        ? t.committee.desk.progress(f.plain(progress * 100, 0), since)
        : null,
      rows: seats.map((seat) => ({
        key: seat.key,
        label: t.committee.desk[seat.key],
        state: seat.state,
        word: word[seat.state],
        // The catalyst's read is the one thing a live seat can be quoted on. The
        // arguments are written in full seconds later, and half a bull case attributed
        // to a researcher still writing it would be a quote nobody said.
        text: seat.state === "in" && seat.key === "catalyst" && flight?.lean
          ? t.committee.desk.read(flight.lean, f.plain(flight.confidence ?? 0, 2))
          : null,
      })),
      note: t.committee.desk.note,
      idle: sitting ? null : idleFor(),
      archived: t.committee.desk.archived(cards.length),
    };

    /** Why the desk is empty — never merely that it is. */
    function idleFor(): DeskIdle {
      if (kind === "disconnected") {
        return { title: t.committee.desk.offline,
                 detail: t.committee.desk.offlineDetail, tone: "text-fail" };
      }
      if (kind === "closed") {
        return { title: t.committee.desk.closed,
                 detail: t.committee.desk.idleNever, tone: "text-ink/40" };
      }
      if (kind === "silent") {
        return { title: t.committee.desk.silent,
                 detail: t.committee.desk.silentDetail, tone: "text-amber" };
      }
      const last = cards[0];
      return {
        title: t.committee.desk.idle,
        detail: last ? t.committee.desk.idleDetail(last.ago) : t.committee.desk.idleNever,
        tone: "text-ink/40",
      };
    }
  }, [sitting, done, flight, now, cards, kind, t, f]);
}

export { DESK };
