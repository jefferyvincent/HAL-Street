/**
 * A payoff curve placed in a box: numbers in, SVG geometry out.
 *
 * Pure, so the shape can be asserted without mounting anything — the same split
 * `spark.ts` uses. The component holds no arithmetic; see `usePayoff`.
 */

import type { PayoffCurve } from "@/lib/payoff";

/** Room for the stroke, so a flat wing sitting on an edge is still a line. */
const PAD = 6;

export interface ShapePoint {
  x: number;
  y: number;
  pnl: number;
}

export interface PayoffShape {
  points: ShapePoint[];
  /** The curve itself. */
  line: string;
  /** The curve closed against the zero line, clipped to one side or the other. */
  gainArea: string | null;
  lossArea: string | null;
  zeroY: number;
  strikes: { strike: number; x: number }[];
  breakevens: { price: number; x: number }[];
  /** Null when no spot was known, or when it sits outside the drawn range. */
  spotX: number | null;
}

/**
 * Where the curve crosses zero between two points, in box coordinates.
 *
 * The areas are clipped at the crossing rather than at the nearer point, because a
 * fill that stops at the last kink leaves a wedge of loss coloured as profit.
 */
function cross(a: ShapePoint, b: ShapePoint): ShapePoint | null {
  if ((a.pnl < 0) === (b.pnl < 0)) return null;
  const t = (0 - a.pnl) / (b.pnl - a.pnl);
  return { x: a.x + t * (b.x - a.x), y: a.y + t * (b.y - a.y), pnl: 0 };
}

/** One side's fill, as a closed path along the zero line. Null when that side is empty. */
function area(points: ShapePoint[], zeroY: number, side: "gain" | "loss"): string | null {
  const wanted = (p: ShapePoint) => (side === "gain" ? p.pnl > 0 : p.pnl < 0);
  const runs: ShapePoint[][] = [];
  let run: ShapePoint[] = [];

  for (let i = 0; i < points.length; i++) {
    const p = points[i]!;
    if (wanted(p)) {
      if (!run.length && i > 0) {
        const c = cross(points[i - 1]!, p);
        if (c) run.push(c);
      }
      run.push(p);
      continue;
    }
    if (run.length) {
      const c = cross(points[i - 1]!, p);
      if (c) run.push(c);
      runs.push(run);
      run = [];
    }
  }
  if (run.length) runs.push(run);
  if (!runs.length) return null;

  return runs
    .map((r) => `M ${r[0]!.x} ${zeroY} ` + r.map((p) => `L ${p.x} ${p.y}`).join(" ")
      + ` L ${r[r.length - 1]!.x} ${zeroY} Z`)
    .join(" ");
}

export function payoffShape(curve: PayoffCurve | null, width: number, height: number,
                            spot: number | null): PayoffShape | null {
  if (!curve || curve.points.length < 2) return null;

  const span = curve.hi - curve.lo || 1;
  const values = curve.points.map((p) => p.pnl);
  const top = Math.max(...values, 0);
  const bottom = Math.min(...values, 0);
  // A structure that only ever gains still needs a zero line to gain *from*, hence
  // the 0 in both bounds above; the range can still be zero if every point is flat.
  const range = top - bottom || 1;

  const x = (s: number) => PAD + ((s - curve.lo) / span) * (width - PAD * 2);
  const y = (pnl: number) => PAD + ((top - pnl) / range) * (height - PAD * 2);

  const points: ShapePoint[] = curve.points.map((p) => ({ x: x(p.s), y: y(p.pnl), pnl: p.pnl }));
  const zeroY = y(0);

  const onChart = spot !== null && spot >= curve.lo && spot <= curve.hi;

  return {
    points,
    line: points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" "),
    gainArea: area(points, zeroY, "gain"),
    lossArea: area(points, zeroY, "loss"),
    zeroY,
    strikes: curve.strikes.map((strike) => ({ strike, x: x(strike) })),
    breakevens: curve.breakevens.map((price) => ({ price, x: x(price) })),
    spotX: onChart ? x(spot) : null,
  };
}
