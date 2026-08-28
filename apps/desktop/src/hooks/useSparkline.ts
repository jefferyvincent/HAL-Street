import { useId } from "react";

import { CHART_COLOR } from "@/constants/theme";
import { sparkGeometry, type Spark } from "@/lib/spark";

export interface Sparkline extends Spark {
  /** Unique per instance, so two sparklines on one screen keep their own gradient. */
  gradientId: string;
  stroke: string;
  grid: string;
}

/**
 * A sparkline's geometry and colours, so the component holds only the SVG.
 *
 * Null when there is nothing to draw — a single reading is a dot, not a line, and
 * the caller renders nothing rather than a shape asserting a trend from one point.
 */
export function useSparkline(points: number[], width: number, height: number): Sparkline | null {
  const id = useId();
  const shape = sparkGeometry(points, width, height);
  if (!shape) return null;

  return {
    ...shape,
    gradientId: `spark-${id}`,
    stroke: shape.up ? CHART_COLOR.up : CHART_COLOR.down,
    grid: CHART_COLOR.grid,
  };
}
