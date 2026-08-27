import { useEffect, useRef } from "react";
import {
  createChart,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { CHART_COLOR } from "@/constants/theme";
import { chartShape } from "@/lib/chartShape";
import type { Candle, Line, Series } from "./useStructureLevels";

/**
 * The canvas lifecycle for a structure chart. Imperative, so it lives here and not
 * inside markup.
 *
 * The three levels are drawn as price lines on the series rather than as extra series:
 * a price line is horizontal by construction and carries its own axis label, which is
 * what makes the target and stop readable at a glance.
 *
 * The chart scales to the prices, not to the levels — which is a reversal.
 *
 * Forcing every level into view sounds right and ruins the chart. A stop sits three
 * times the credit away from entry, so on a spread trading between -1.0 and -1.7 the
 * range is dragged out to -4.53 and every candle collapses into a sliver: the thing
 * the chart exists to show becomes the thing you cannot see. The levels are drawn as
 * price lines and appear when the price is anywhere near them, which is exactly when
 * they matter, and their numbers sit in the cells above the chart at all times.
 *
 * Scroll and zoom are enabled for the same reason, so a level off the bottom can be
 * found rather than merely inferred.
 */
export function useStructureChartCanvas(
  series: Series[], candles: Candle[], lines: Line[], live: number | null,
  fit: "working" | "levels" = "working",
) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const line = useRef<ISeriesApi<"Line"> | null>(null);
  const bars = useRef<ISeriesApi<"Candlestick"> | null>(null);
  //: The shape of the data the time scale was last fitted to. See below.
  const fitted = useRef<string>("");

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
      rightPriceScale: { borderColor: CHART_COLOR.border },
      timeScale: {
        borderColor: CHART_COLOR.border, timeVisible: true, secondsVisible: false,
        // Room to the right of the newest bar, so the candle still being written is
        // not pressed against the frame — which is where it is hardest to read and
        // where its wick gets clipped.
        rightOffset: 6,
      },
      crosshair: {
        horzLine: { color: CHART_COLOR.crosshair, labelBackgroundColor: CHART_COLOR.crosshair },
        vertLine: { color: CHART_COLOR.crosshair, labelBackgroundColor: CHART_COLOR.crosshair },
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true,
                      vertTouchDrag: true },
      handleScale: { mouseWheel: true, pinch: true, axisPressedMouseMove: true },
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
      crosshairMarkerVisible: false,
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
    bars.current?.setData(candles.map((c) => {
      // The forming candle is extended by the live mark rather than left at the
      // last bar it was built from. Its close *is* the current price, and its range
      // has to grow to contain it, or the candle draws a body that excludes a value
      // the structure is at right now.
      const close = c.forming && live !== null ? live : c.close;
      const high = c.forming && live !== null ? Math.max(c.high, live) : c.high;
      const low = c.forming && live !== null ? Math.min(c.low, live) : c.low;
      return {
        time: c.time as UTCTimestamp,
        open: c.open, high, low, close,
        // Hollow, but still green or red. Painting it amber said "unfinished" and
        // took the direction with it — and direction is most of what a candle is
        // for. A transparent body against a coloured border and wick says both.
        ...(c.forming
          ? {
              color: "transparent",
              borderColor: close >= c.open ? CHART_COLOR.up : CHART_COLOR.down,
              wickColor: close >= c.open ? CHART_COLOR.up : CHART_COLOR.down,
            }
          : {}),
      };
    }));

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

    // Fit only when the data behind the chart actually changed — a new structure, a
    // new bar size, a new bar — and never merely because the live mark ticked.
    //
    // It used to fit on every run of this effect, which is every render. Two things
    // came of that: a scroll or a zoom was undone within seconds, and the view was
    // reset continuously rather than at the moments a reset means something. The
    // symptom is the opposite of what it sounds like — a chart that re-fits constantly
    // reads as one that never settles where you left it.
    //
    // Keyed on the shape rather than the values, so the forming candle growing by a
    // cent is not a new chart while a switch from 1Hour to 15Min is. See `chartShape`.
    const shape = chartShape(series, candles, lines);
    const reshaped = shape !== fitted.current;
    fitted.current = shape;

    if (series.length && reshaped) {
      chart.current?.timeScale().fitContent();
      // `fitContent` collapses the offset it was given; put it back.
      chart.current?.timeScale().applyOptions({ rightOffset: 6 });
    }

    if (series.length) {
      // Prices first, then whichever levels can join them without flattening the
      // chart. Including everything is geometry, not preference: a stop four times
      // the candle range away *must* squash the candles into a fifth of the height,
      // and a target sitting right beside them costs nothing. So the default takes
      // the price action plus any level within one range of it — which is entry and
      // target on every structure this agent builds — and leaves the stop to the
      // toggle, named in the legend meanwhile.
      const prices = candles.flatMap((c) => [c.high, c.low])
        .concat(series.map((p) => p.value))
        .concat(live === null ? [] : [live]);

      if (prices.length) {
        const floor = Math.min(...prices);
        const ceiling = Math.max(...prices);
        const span = ceiling - floor || 0.1;
        const near = fit === "levels"
          ? lines.map((l) => l.value)   // everything, asked for explicitly
          : lines.map((l) => l.value).filter(
              (v) => v >= floor - span && v <= ceiling + span);

        const values = prices.concat(near);
        const low = Math.min(...values);
        const high = Math.max(...values);
        const pad = (high - low) * 0.08 || 0.1;
        api.applyOptions({ autoscaleInfoProvider: () => ({
          priceRange: { minValue: low - pad, maxValue: high + pad },
        }) });
      }
    }

    return () => {
      drawn.forEach((l) => api.removePriceLine(l));
      if (marker) api.removePriceLine(marker);
    };
  }, [series, candles, lines, live, fit]);

  return host;
}
