import { useMemo, useRef } from "react";
import { STROKE } from "@/constants/theme";
import { useStrings } from "@/hooks/useStrings";
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
  /** Still open. Drawn hollow, and updated by the live mark between polls. */
  forming: boolean;
}

/**
 * The chart's data, derived once: the price line, the three level lines, and the
 * bounds that keep all of them on screen.
 *
 * The bounds matter more than they look. A stop sits three times the credit away from
 * entry, so a chart auto-scaled to the price series alone would put it off-screen —
 * and a stop line you cannot see is the one thing this view exists to show.
 */
/**
 * The candle for the bucket the clock is in, when the broker has not published a
 * bar for it yet.
 *
 * There is always a gap: a 15-minute bar for 18:00 does not exist at 18:03, so the
 * newest candle is the *previous* bucket and nothing on the chart is forming — even
 * though a live mark for right now is in hand. This builds that candle out of the
 * marks as they arrive, keeping its high and low across polls so it grows the way a
 * real one does rather than resetting to a dot every twenty seconds.
 *
 * Reset whenever the bucket turns over, so yesterday's extremes never leak into
 * today's candle.
 */
function useFormingCandle(live: number | null, bucketMs: number) {
  const held = useRef<{ candle: Candle; bucketMs: number } | null>(null);
  if (live === null || !Number.isFinite(live)) return null;

  const time = Math.floor(Date.now() / bucketMs) * (bucketMs / 1000);
  const current = held.current;

  // A different bar size is a different candle, not the same one continued. Without
  // this, switching the timeframe kept growing the candle built under the old one and
  // carried its high and low across — so the chart you came back to was not the chart
  // you left.
  const same = current && current.bucketMs === bucketMs && current.candle.time === time;

  if (same) {
    const candle = current.candle;
    const high = Math.max(candle.high, live);
    const low = Math.min(candle.low, live);
    // The identity matters as much as the values. This is a `useMemo` dependency, and
    // returning a fresh object every render re-derived the entire series and re-ran
    // the canvas effect — which calls `fitContent`. The chart was being re-fitted on
    // every render whether or not anything had moved, so it never held still and any
    // scroll or zoom was undone within seconds.
    if (high === candle.high && low === candle.low && candle.close === live) {
      return candle;
    }
    held.current = { bucketMs, candle: { ...candle, high, low, close: live } };
  } else {
    held.current = {
      bucketMs,
      candle: { time, open: live, high: live, low: live, close: live, forming: true },
    };
  }
  return held.current.candle;
}

export function useStructureLevels(chart: StructureChart | null, live: number | null = null) {
  const t = useStrings();
  // The bucket the server grouped by, inferred from what it sent: hourly stamps
  // carry a time, daily ones do not. Reading it off the data avoids a second place
  // that has to agree with `resolution()`.
  const hourly = (chart?.candles?.[0]?.t ?? "").length > 11;
  const forming = useFormingCandle(live, hourly ? 3_600_000 : 86_400_000);
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
        { key: "entry", value: Number(entry), color: STROKE.ink, label: t.chart.entry },
        { key: "target", value: Number(target), color: STROKE.pass, label: t.chart.target },
        {
          key: "stop",
          value: Number(stop),
          color: STROKE.fail,
          // A stop that cannot print is still the level the policy names; saying so
          // beats drawing it as though the market could get there.
          label: stop_reachable === false ? t.chart.stopUnreachable : t.chart.stop,
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
      candles.push({
        time, open: values[0]!, high: values[1]!, low: values[2]!, close: values[3]!,
        forming: Boolean(c.forming),
      });
    }

    return {
      series,
      candles: forming && (candles.length === 0 || forming.time > candles[candles.length - 1]!.time)
        ? [...candles, forming]
        : candles,
      lines: lines.filter((l) => Number.isFinite(l.value)),
      last: series.length ? series[series.length - 1]!.value : null,
    };
  }, [chart, t, forming]);
}
