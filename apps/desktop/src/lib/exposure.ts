/**
 * How a position's direction is labelled and coloured.
 *
 * The rule is one line and the reason it lives here is not. The exposure chip sits on
 * the same card as the structure chart, and they are charts of different things: the
 * chip is about the *underlying* ("wants SPY up"), the chart is about the *spread's
 * own mark*, which for a credit structure rises toward zero as it wins. Both were
 * saying "up" for the put spread and disagreeing for the call spread, which reads as
 * one of them being inverted.
 *
 * Neither was. The fix is that the chip names its instrument — `book.exposure.*` takes
 * the symbol — so the two claims are visibly about two different quantities. The part
 * that is a rule rather than a string is here, where a test can reach it.
 */
import { STROKE } from "@/constants/theme";

export type ExposureKind = "bullish" | "bearish" | "neutral" | "unknown";

const KINDS: ExposureKind[] = ["bullish", "bearish", "neutral", "unknown"];

/** One of the four, or `unknown` for anything else — never the raw string. */
export function exposureKind(raw: string | null | undefined): ExposureKind {
  return KINDS.includes(raw as ExposureKind) ? (raw as ExposureKind) : "unknown";
}

/**
 * The chip's colour: what the position wants, not what it is doing.
 *
 * Neutral and unknown are muted rather than warned. A condor painted red reads as a
 * position in trouble when it is a position doing what it was opened to do.
 */
export function exposureTone(kind: ExposureKind): string {
  if (kind === "bullish") return STROKE.pass;
  if (kind === "bearish") return STROKE.fail;
  return STROKE.muted;
}
