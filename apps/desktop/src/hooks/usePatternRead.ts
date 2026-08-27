import { useMemo } from "react";
import { useStrings } from "@/hooks/useStrings";
import { STROKE } from "@/constants/theme";
import type { Position } from "@/types";

export interface PatternRead {
  exposure: string;
  /** Colour for the exposure chip: what the position wants, not what it is doing. */
  tone: string;
  /** One line per pattern, already ordered: what bears on the position first. */
  lines: { key: string; text: string; tone: string }[];
  title: string;
  quiet: boolean;
}

/**
 * A position's chart read, shaped for display.
 *
 * Ordered rather than filtered: everything the detector confirmed is shown, with
 * what runs *against* the position first. Hiding the confirming ones would make the
 * badge look like a warning system, which it is not — the exit policy never reads
 * any of this, and a reader who only ever sees bad news starts treating the badge
 * as an alarm and then as noise.
 *
 * "Chart quiet" is a real answer and the common one. Confirmation-gating means most
 * days name nothing, and saying so beats an empty space that could equally mean the
 * feature is broken.
 */
export function usePatternRead(position: Position): PatternRead {
  const t = useStrings();
  return useMemo(() => {
    const exposure = position.exposure ?? "unknown";
    const against = position.against ?? [];
    const confirming = position.confirming ?? [];
    const all = position.patterns ?? [];
    const neither = all.filter(
      (p) => !against.includes(p) && !confirming.includes(p),
    );

    const line = (tone: string) => (p: { name: string; note: string }) => ({
      key: p.name,
      text: `${p.name} — ${p.note}`,
      tone,
    });

    return {
      exposure: t.book.exposure[exposure as keyof typeof t.book.exposure] ?? exposure,
      tone: exposure === "bullish" ? STROKE.pass
        : exposure === "bearish" ? STROKE.fail
        : STROKE.muted,
      lines: [
        ...against.map(line(STROKE.fail)),
        ...confirming.map(line(STROKE.pass)),
        ...neither.map(line(STROKE.muted)),
      ],
      title: t.book.patternsTitle(position.underlying),
      quiet: all.length === 0,
    };
  }, [position, t]);
}
