import { useMemo } from "react";

import { STROKE } from "@/constants/theme";
import { useFormat } from "@/hooks/useFormat";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

export interface Side {
  /** The argument itself, or "" when the arm did not answer. */
  text: string;
  /** Why it did not, when it did not. Drawn instead of the text. */
  absent: string | null;
  /** The record kept only the first part of it. The judge heard all of it. */
  clipped: boolean;
}

export interface StageCost {
  key: string;
  stage: string;
  /** "1,204/380" — in over out, for the stage. */
  spend: string;
  /** Which model spent it, where the record says. */
  model: string | null;
}

export interface CommitteeCard {
  key: string;
  underlying: string;
  /** The raw stamp, kept beside the rendered ones so callers can group by pass. */
  ts: string;
  headlines: string;
  time: string;
  ago: string;
  /** What the judge did, as a label and a colour. */
  verdict: { label: string; tone: string };
  /** What the gates then did with it, or null when nothing was proposed to gate. */
  gated: { label: string; ok: boolean } | null;
  catalyst: {
    absent: string | null;
    lean: { label: string; tone: string } | null;
    confidence: string;
    note: string;
  };
  bull: Side;
  bear: Side;
  reflection: { key: string; text: string }[];
  judge: {
    error: string | null;
    structure: string | null;
    rationale: string;
    /** The gates' verdict, or the words for a proposal that never reached them. */
    outcome: string;
    tokens: string;
  };
  stages: StageCost[];
}

/**
 * The committee sessions, shaped for the tree.
 *
 * The failures are the part worth deriving rather than reading off. A stage that
 * did not answer is journalled as `bull: <reason>` in a flat list of strings, and
 * an arm of the tree drawn empty is indistinguishable from an arm that had nothing
 * to say — which matters here, because a missing researcher means the judge decided
 * having heard one side, and that is a fact about the decision rather than a glitch.
 */
export function useCommittee(): CommitteeCard[] {
  const t = useStrings();
  const f = useFormat();
  const sessions = useConnection((s) => s.snapshot?.committees) ?? [];

  return useMemo(() => sessions.map((session) => {
    const o = session.outcome;
    const verdict = o.error
      ? { label: t.committee.failed, tone: STROKE.fail }
      : o.passed
        ? { label: t.committee.passed, tone: STROKE.muted }
        : { label: t.committee.proposed, tone: STROKE.amber };

    const gated = o.approved === null
      ? null
      : o.approved
        ? { label: t.committee.approved, ok: true }
        : { label: t.committee.rejected(o.rejected_by.join(t.common.listSep)), ok: false };

    const reason = (side: string) =>
      session.errors.find((e) => e.startsWith(`${side}:`))?.slice(side.length + 1).trim()
      ?? null;

    const lean = session.catalyst?.lean ?? null;

    return {
      key: `${session.underlying}@${session.ts}`,
      underlying: session.underlying,
      ts: session.ts,
      headlines: t.committee.headlines(session.headlines),
      // Both, because they answer different questions: "when" and "how long ago". A
      // wall clock alone makes a card from two hours back look as current as one from
      // two minutes back.
      time: f.clock(session.ts),
      ago: f.ago(session.ts),
      verdict,
      gated,
      catalyst: {
        absent: session.catalyst?.note?.startsWith("unavailable")
          ? session.catalyst.note : reason("catalyst"),
        lean: lean === null ? null : {
          // The catalyst's own word, translated where we know it. It is model output,
          // so an unknown one is shown as it came rather than dropped.
          label: t.committee.lean[lean] ?? lean.toUpperCase(),
          tone: lean === "bullish" ? "text-pass"
            : lean === "bearish" ? "text-fail"
            : "text-ink/45",
        },
        confidence: t.committee.confidence(
          session.catalyst?.confidence?.toFixed(2) ?? t.common.dash),
        note: session.catalyst?.note ?? "",
      },
      bull: { text: session.bull, clipped: (session.clipped ?? []).includes("bull"),
              absent: session.bull ? null : reason("bull") ?? t.committee.silent },
      bear: { text: session.bear, clipped: (session.clipped ?? []).includes("bear"),
              absent: session.bear ? null : reason("bear") ?? t.committee.silent },
      reflection: session.reflection.map((r) => ({
        key: r.structure,
        text: t.committee.reflectionRow(
          r.structure, r.realized_usd ?? t.common.unknown, r.outcome),
      })),
      judge: {
        error: o.error ?? null,
        structure: o.structure ?? null,
        rationale: o.rationale,
        outcome: gated?.label ?? t.committee.ungated,
        tokens: t.committee.tokens(session.tokens.out ?? 0),
      },
      // Where the tokens went, and which model spent them. A single total said the
      // committee was expensive without saying which quarter of it to look at.
      stages: Object.entries(session.stages ?? {}).map(([stage, spend]) => ({
        key: stage,
        stage,
        spend: t.committee.stageSpend(f.plain(spend.in, 0), f.plain(spend.out, 0)),
        model: spend.model ?? null,
      })),
    };
  }), [sessions, t, f]);
}

/**
 * Whether a cycle is running right now, and what to say about it.
 *
 * The committee is the slowest stage in the system — three model calls deep — so
 * between "nothing here yet" and a finished card there was a minute of blank screen
 * that read as a broken tab.
 */
export function useCommitteeStatus(): { busy: boolean; label: string } {
  const t = useStrings();
  const busy = useConnection((s) => s.snapshot?.in_flight) ?? null;

  if (!busy) return { busy: false, label: t.committee.waiting };
  return {
    busy: true,
    // The stage in the agent's own words, not a second coarser one beside it. The
    // header said "deliberating SPY" while the card under it said "the judge
    // deciding" — both true, one of them stale by three model calls.
    label: busy.underlying
      ? t.committee.working(busy.stage, busy.underlying)
      : t.committee.workingAny,
  };
}
