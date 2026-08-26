import { useEffect, useMemo, useRef } from "react";
import { createChart, type IChartApi, type ISeriesApi, type UTCTimestamp } from "lightweight-charts";
import { move, toPoints } from "@/lib/equity";
import type { EquityPoint, Pnl } from "@/types";

/**
 * The chart's whole lifecycle: create once, feed on every push, dispose on unmount.
 *
 * It lives in a hook rather than inside the component because none of it is markup —
 * it is an imperative canvas API being driven from React state, and the two do not
 * belong in the same file. The component receives a ref to attach and nothing else.
 */
export function useEquityChart(curve: EquityPoint[], pnl: Pnl) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Area"> | null>(null);

  const points = useMemo(() => toPoints(curve), [curve]);
  const drawable = points.length >= 2;

  useEffect(() => {
    if (!host.current || !drawable) return;
    const c = createChart(host.current, {
      autoSize: true,
      layout: {
        background: { color: "transparent" },
        textColor: "rgba(233,237,240,.4)",
        fontSize: 10,
        fontFamily: '"IBM Plex Mono", ui-monospace, monospace',
      },
      grid: { vertLines: { color: "#1f252a" }, horzLines: { color: "#1f252a" } },
      rightPriceScale: { borderColor: "#23292e" },
      timeScale: { borderColor: "#23292e", timeVisible: true, secondsVisible: false },
      crosshair: {
        horzLine: { color: "#e8a33d", labelBackgroundColor: "#e8a33d" },
        vertLine: { color: "#e8a33d", labelBackgroundColor: "#e8a33d" },
      },
      // Panning and zooming a 150px strip is fiddly and there is nothing off-screen
      // to reach: the server already trims the curve to what fits.
      handleScale: false,
      handleScroll: false,
    });
    series.current = c.addAreaSeries({
      lineColor: "#e8a33d",
      topColor: "rgba(232,163,61,.22)",
      bottomColor: "rgba(232,163,61,0)",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    chart.current = c;
    return () => {
      c.remove();
      chart.current = null;
      series.current = null;
    };
  }, [drawable]);

  useEffect(() => {
    if (!series.current) return;
    series.current.setData(points.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })));
    chart.current?.timeScale().fitContent();
  }, [points]);

  return {
    host,
    drawable,
    count: points.length,
    move: move(pnl.equity_start, pnl.equity_last),
  };
}
