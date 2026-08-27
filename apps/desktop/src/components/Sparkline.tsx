import { useId } from "react";
import { CHART_COLOR } from "@/constants/theme";

/**
 * A position's P&L over the cycles the agent has looked at it.
 *
 * **P&L, not the mark, and the distinction is the whole reason this is safe to draw.**
 * Every structure this agent opens is a credit: it is sold for -1.51 and bought back
 * cheaper, so its mark rises as the position *loses*. A line of marks would slope
 * downward on a winning trade and upward on a losing one, coloured green while it
 * fell — a chart that means the opposite of what it looks like. P&L has one sense on
 * every structure ever built: up is good.
 *
 * Drawn from the agent's own marks, one per cycle, which is why it is a shape rather
 * than a tick chart — the spacing is however often the desk looked. The card stamps
 * the last read's age beside it and the full history is one click away.
 *
 * Plain SVG. A charting library for forty points in a hundred pixels would cost more
 * than it explained.
 */
export function Sparkline({ points, width = 104, height = 26 }: {
  points: number[]; width?: number; height?: number;
}) {
  const id = useId();
  if (points.length < 2) return null;

  const low = Math.min(...points, 0);
  const high = Math.max(...points, 0);
  // A flat line still has to sit somewhere, and dividing by its zero range would put
  // it at infinity. Half a cent of span is enough to place it in the middle.
  const span = high - low || 0.01;
  const pad = 2;
  const usable = height - pad * 2;
  const x = (i: number) => (i / (points.length - 1)) * width;
  const y = (v: number) => pad + (1 - (v - low) / span) * usable;

  const last = points[points.length - 1]!;
  const up = last >= 0;
  const stroke = up ? CHART_COLOR.up : CHART_COLOR.down;
  const line = points.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  // Break-even, drawn whenever the line has been on both sides of it. On a position
  // that has only ever lost, a rule along the top edge says nothing and crowds the
  // shape it is meant to frame.
  const crossed = low < 0 && high > 0;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}
         className="shrink-0 overflow-visible" aria-hidden focusable="false">
      <defs>
        <linearGradient id={`spark-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.28" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>

      {crossed && (
        <line x1="0" y1={y(0)} x2={width} y2={y(0)}
              stroke={CHART_COLOR.grid} strokeWidth="1" strokeDasharray="2 2" />
      )}

      {/* The fill is under the line and clipped to it, so the shape reads at a glance
          without the line itself getting lost in it. */}
      <polygon points={`0,${height} ${line} ${width},${height}`}
               fill={`url(#spark-${id})`} />
      <polyline points={line} fill="none" stroke={stroke} strokeWidth="1.25"
                strokeLinejoin="round" strokeLinecap="round" />
      {/* Where it is now, which is the point the eye should land on. */}
      <circle cx={x(points.length - 1)} cy={y(last)} r="1.9" fill={stroke} />
    </svg>
  );
}
