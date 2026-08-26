import type { EquityPoint } from "@/types";

export interface Point {
  time: number;
  value: number;
}

/**
 * Equity readings to chart points. Pure, so it can be reasoned about (and tested)
 * without a canvas.
 *
 * Two corrections happen here and nowhere else. Values arrive as decimal strings and
 * are parsed once, at this edge. And lightweight-charts requires strictly increasing,
 * unique timestamps — two scans inside the same second are real, and would otherwise
 * be silently dropped, so the later one is nudged forward by a second rather than
 * lost. Nudging is a display concession; the journal keeps the true stamps.
 */
export function toPoints(curve: EquityPoint[]): Point[] {
  let last = 0;
  const out: Point[] = [];
  for (const p of curve) {
    const t = Math.floor(new Date(p.t).getTime() / 1000);
    const value = Number(p.v);
    if (!Number.isFinite(t) || !Number.isFinite(value)) continue;
    const time = t <= last ? last + 1 : t;
    last = time;
    out.push({ time, value });
  }
  return out;
}

/** Start-to-latest move in dollars, or null when there is not yet a start. */
export function move(start: string | null, latest: string | null): number | null {
  const a = Number(start);
  const b = Number(latest);
  return Number.isFinite(a) && Number.isFinite(b) ? b - a : null;
}
