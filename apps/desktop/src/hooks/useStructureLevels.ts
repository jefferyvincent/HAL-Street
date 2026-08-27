import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { STROKE } from "@/constants/theme";
import type { StructureChart } from "@/types";

export interface Line {
  key: "entry" | "target" | "stop";
  value: number;
  color: string;
  label: string;
  /**
   * A level the market cannot reach. Drawn dashed and labelled, rather than dropped:
   * the reader should see that the policy names a stop *and* that this structure
   * cannot hit it, which is a fact about the position worth knowing.
   */
  unreachable?: boolean;
}

export interface Series {
  time: number;
  value: number;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
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
  const { t } = useTranslation();
  return useMemo(() => {
    if (!chart) {
      return {
        series: [] as Series[], candles: [] as Candle[],
        lines: [] as Line[], last: null as number | null,
      };
    }

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
      const { entry, target, stop, stop_reachable } = chart.levels;
      lines.push(
        { key: "entry", value: Number(entry), color: STROKE.ink, label: t("chart.entry") },
        { key: "target", value: Number(target), color: STROKE.pass, label: t("chart.target") },
        {
          key: "stop",
          value: Number(stop),
          color: STROKE.fail,
          // A stop that cannot print is still the level the policy names; saying so
          // beats drawing it as though the market could get there.
          label: stop_reachable === false ? t("chart.stopUnreachable") : t("chart.stop"),
          unreachable: stop_reachable === false,
        },
      );
    }

    let previousCandle = 0;
    const candles: Candle[] = [];
    for (const c of chart.candles ?? []) {
      const seconds = Math.floor(new Date(c.t).getTime() / 1000);
      const values = [Number(c.o), Number(c.h), Number(c.l), Number(c.c)];
      if (!Number.isFinite(seconds) || values.some((v) => !Number.isFinite(v))) continue;
      const time = seconds <= previousCandle ? previousCandle + 1 : seconds;
      previousCandle = time;
      candles.push({ time, open: values[0]!, high: values[1]!, low: values[2]!, close: values[3]! });
    }

    return {
      series,
      candles,
      lines: lines.filter((l) => Number.isFinite(l.value)),
      last: series.length ? series[series.length - 1]!.value : null,
    };
  }, [chart, t]);
}
