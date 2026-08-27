import { useEffect, useRef } from "react";
import {
  createChart,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { CHART_COLOR } from "@/constants/theme";
import type { Candle, Line, Series } from "./useStructureLevels";

/**
 * The canvas lifecycle for a structure chart. Imperative, so it lives here and not
 * inside markup.
 *
 * The three levels are drawn as price lines on the series rather than as extra series:
 * a price line is horizontal by construction and carries its own axis label, which is
 * what makes the target and stop readable at a glance.
 *
 * The visible range is forced to include every level. Auto-scaling to the price alone
 * would push a stop — three times the credit from entry — off the bottom, and an
 * invisible stop defeats the point of drawing one.
 */
export function useStructureChartCanvas(
  series: Series[], candles: Candle[], lines: Line[], live: number | null,
) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const line = useRef<ISeriesApi<"Line"> | null>(null);
  const bars = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    if (!host.current) return;
    const c = createChart(host.current, {
      autoSize: true,
      layout: {
        background: { color: "transparent" },
        textColor: CHART_COLOR.text,
        fontSize: 10,
        fontFamily: '"IBM Plex Mono", ui-monospace, monospace',
      },
      grid: { vertLines: { color: CHART_COLOR.grid }, horzLines: { color: CHART_COLOR.grid } },
      rightPriceScale: { borderColor: CHART_COLOR.border, scaleMargins: { top: 0.12, bottom: 0.12 } },
      timeScale: { borderColor: CHART_COLOR.border, timeVisible: true, secondsVisible: false },
      crosshair: {
        horzLine: { color: CHART_COLOR.crosshair, labelBackgroundColor: CHART_COLOR.crosshair },
        vertLine: { color: CHART_COLOR.crosshair, labelBackgroundColor: CHART_COLOR.crosshair },
      },
    });
    // Candles for the sessions, and the hourly line over them. The line is what
    // the levels are read against — a target sitting inside a day's range says
    // nothing about whether the structure was ever *at* it, and the hourly points
    // are the finest thing actually observed.
    bars.current = c.addCandlestickSeries({
      upColor: CHART_COLOR.up, downColor: CHART_COLOR.down,
      borderUpColor: CHART_COLOR.up, borderDownColor: CHART_COLOR.down,
      wickUpColor: CHART_COLOR.up, wickDownColor: CHART_COLOR.down,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    line.current = c.addLineSeries({
      color: CHART_COLOR.line,
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    chart.current = c;
    return () => {
      c.remove();
      chart.current = null;
      line.current = null;
      bars.current = null;
    };
  }, []);

  useEffect(() => {
    const api = line.current;
    if (!api) return;

    api.setData(series.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })));
    bars.current?.setData(candles.map((c) => ({
      time: c.time as UTCTimestamp,
      open: c.open, high: c.high, low: c.low, close: c.close,
    })));

    // The live mark, drawn on the price axis where the last traded value sits. It
    // is the only line here that moves between renders, which is why it is added
    // with the rest and removed with them rather than kept across effects.
    const marker = live === null ? null : api.createPriceLine({
      price: live,
      color: CHART_COLOR.liveLine,
      lineWidth: 1,
      lineStyle: LineStyle.LargeDashed,
      axisLabelVisible: true,
      title: "LIVE",
    });

    const drawn = lines.map((l) =>
      api.createPriceLine({
        price: l.value,
        color: l.color,
        lineWidth: 1,
        // Solid for where the position went in; dashed for a level the policy is
        // waiting on; dotted for one it names but the market cannot print, so the
        // reader can tell "not yet" from "not ever" without reading the label.
        lineStyle: l.unreachable
          ? LineStyle.Dotted
          : l.key === "entry"
            ? LineStyle.Solid
            : LineStyle.Dashed,
        axisLabelVisible: true,
        title: l.label,
      }),
    );

    if (series.length) {
      chart.current?.timeScale().fitContent();
      // Every level in view, whatever the price did.
      const values = series.map((p) => p.value)
        .concat(candles.flatMap((c) => [c.high, c.low]))
        .concat(lines.map((l) => l.value))
        .concat(live === null ? [] : [live]);
      const low = Math.min(...values);
      const high = Math.max(...values);
      const pad = (high - low) * 0.08 || 0.1;
      api.applyOptions({ autoscaleInfoProvider: () => ({
        priceRange: { minValue: low - pad, maxValue: high + pad },
      }) });
    }

    return () => {
      drawn.forEach((l) => api.removePriceLine(l));
      if (marker) api.removePriceLine(marker);
    };
  }, [series, candles, lines, live]);

  return host;
}
