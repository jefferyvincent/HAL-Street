/**
 * The geometry of a sparkline: points in, path strings out.
 *
 * Pure, so the shape of a line can be asserted without mounting anything. The
 * component that draws it holds no arithmetic — see `useSparkline`.
 */

export interface Spark {
  /** The polyline's points, ready for the attribute. */
  line: string;
  /** The same line closed against the floor, for the gradient fill. */
  area: string;
  /** Where the last reading sits, which is the point the eye should land on. */
  dot: { x: number; y: number };
  /** Break-even, or null when the line has never been on both sides of it. */
  zeroY: number | null;
  /** Whether the last reading is a gain. Decides the colour. */
  up: boolean;
}

/**
 * A line needs two points; anything less is not a shape and returns null.
 *
 * The pad keeps the stroke off the edge, and a flat line still has to sit somewhere —
 * dividing by its zero range would put it at infinity, so half a cent of span stands
 * in and places it in the middle.
 */
export function sparkGeometry(points: number[], width: number, height: number): Spark | null {
  if (points.length < 2) return null;

  const low = Math.min(...points, 0);
  const high = Math.max(...points, 0);
  const span = high - low || 0.01;
  const pad = 2;
  const usable = height - pad * 2;
  const x = (i: number) => (i / (points.length - 1)) * width;
  const y = (v: number) => pad + (1 - (v - low) / span) * usable;

  const last = points[points.length - 1]!;
  const line = points.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");

  return {
    line,
    area: `0,${height} ${line} ${width},${height}`,
    dot: { x: x(points.length - 1), y: y(last) },
    // Drawn only where it falls inside the shape. On a position that has only ever
    // lost, a rule along the top edge says nothing and crowds what it should frame.
    zeroY: low < 0 && high > 0 ? y(0) : null,
    up: last >= 0,
  };
}
