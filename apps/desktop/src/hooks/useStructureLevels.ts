import { useMemo } from "react";
import { STROKE } from "@/constants/theme";
import type { StructureChart } from "@/types";

export interface Line {
  key: "entry" | "target" | "stop";
  value: number;
  color: string;
  label: string;
}

export interface Series {
  time: number;
  value: number;
}

/**
 * The chart's data, derived once: the price line, the three level lines, and the
 * bounds that keep all of them on screen.
 *
 * The bounds matter more than they look. A stop sits three times the credit away from
 * entry, so a chart auto-scaled to the price series alone would put it off-screen —
 * and a stop line you cannot see is the one thing this view exists to show.
 */
export function useStructureLevels(chart: StructureChart | null) {
  return useMemo(() => {
    if (!chart) return { series: [] as Series[], lines: [] as Line[], last: null as number | null };

    let previous = 0;
    const series: Series[] = [];
    for (const point of chart.series) {
      const seconds = Math.floor(new Date(point.t).getTime() / 1000);
      const value = Number(point.v);
      if (!Number.isFinite(seconds) || !Number.isFinite(value)) continue;
      // lightweight-charts requires strictly increasing, unique stamps.
      const time = seconds <= previous ? previous + 1 : seconds;
      previous = time;
      series.push({ time, value });
    }

    const lines: Line[] = [];
    if (chart.levels) {
      const { entry, target, stop } = chart.levels;
      lines.push(
        { key: "entry", value: Number(entry), color: STROKE.ink, label: "ENTRY" },
        { key: "target", value: Number(target), color: STROKE.pass, label: "TARGET" },
        { key: "stop", value: Number(stop), color: STROKE.fail, label: "STOP" },
      );
    }

    return {
      series,
      lines: lines.filter((l) => Number.isFinite(l.value)),
      last: series.length ? series[series.length - 1]!.value : null,
    };
  }, [chart]);
}
