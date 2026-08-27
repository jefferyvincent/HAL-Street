import { useMemo } from "react";
import { STROKE } from "@/constants/theme";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";
import type { Committee } from "@/types";

export interface CommitteeCard {
  key: string;
  session: Committee;
  /** What the judge did, as a label and a colour. */
  verdict: { label: string; tone: string };
  /** What the gates then did with it, or null when nothing was proposed to gate. */
  gated: { label: string; ok: boolean } | null;
  /** Per-stage failure text, keyed by side, so a missing arm renders as missing. */
  missing: { catalyst: string | null; bull: string | null; bear: string | null };
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
        : { label: t.committee.rejected(o.rejected_by.join(", ")), ok: false };

    const reason = (side: string) =>
      session.errors.find((e) => e.startsWith(`${side}:`))?.slice(side.length + 1).trim()
      ?? null;

    return {
      key: `${session.underlying}@${session.ts}`,
      session,
      verdict,
      gated,
      missing: {
        catalyst: session.catalyst?.note?.startsWith("unavailable")
          ? session.catalyst.note : reason("catalyst"),
        bull: session.bull ? null : reason("bull") ?? t.committee.silent,
        bear: session.bear ? null : reason("bear") ?? t.committee.silent,
      },
    };
  }), [sessions, t]);
}
