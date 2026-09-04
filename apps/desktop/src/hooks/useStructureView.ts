import { useMemo } from "react";

import { exitProgress } from "@/lib/exitProgress";
import { stripRoot } from "@/lib/names";
import { useFormat } from "@/hooks/useFormat";
import { useMarks } from "@/hooks/useMarks";
import { useStrings } from "@/hooks/useStrings";
import { useStructureChartCanvas } from "@/hooks/useStructureChartCanvas";
import { useStructureLevels } from "@/hooks/useStructureLevels";
import { useUI } from "@/stores/ui";
import type { LegMark, StructureChart } from "@/types";

export interface Tile {
  label: string;
  value: string;
  /** The class the figure is drawn in. Reads off the P&L's sign, never the price's. */
  tone: string;
  note?: string | null;
  /** Whether that note is the live-quote one, since only its colour differs. */
  noteLive?: boolean;
}

export interface TimeframeChoice {
  key: string;
  label: string;
  active: boolean;
  select: () => void;
}

/**
 * Everything the structure view shows, assembled away from the markup that shows it.
 *
 * Two things are load-bearing and both are decided here. The colour comes from
 * whether the *position* is winning, not from the price's own sign — every credit
 * structure marks negative, and a sign-based colour would paint them all red for the
 * whole of their life. And NOW leads with the live mark, falling back to the last
 * bar, labelled either way: the series is hourly bars, which is right for the line
 * and wrong for "what is it worth".
 */
export function useStructureView(chart: StructureChart) {
  const t = useStrings();
  const f = useFormat();

  const live = useMarks()?.marks[chart.structure_id];
  const mark = live?.mark == null ? null : Number(live.mark);
  const { series, candles, lines, last } = useStructureLevels(chart, mark);

  const fit = useUI((s) => s.chartFit);
  const toggleFit = useUI((s) => s.toggleFit);
  const timeframe = useUI((s) => s.chartTimeframe);
  const setTimeframe = useUI((s) => s.setTimeframe);
  const host = useStructureChartCanvas(series, candles, lines, mark, fit);

  const view = useMemo(() => {
    const now = live?.mark ?? (last === null ? null : String(last));
    const isLive = live?.mark != null;
    const pnl = live?.unrealized_usd ?? null;
    const tone = pnl === null ? "text-ink" : Number(pnl) >= 0 ? "text-pass" : "text-fail";

    // Which levels the drawn range does not reach. Only meaningful when scaled to the
    // price — asking to fit them is what makes them visible, so under that scale there
    // is nothing to report. A level outside the range is invisible and silent
    // otherwise, and the reader has no way to tell "no stop" from "stop below".
    const drawn = candles.flatMap((c) => [c.high, c.low]);
    const span = drawn.length ? Math.max(...drawn) - Math.min(...drawn) || 0.1 : 0;
    const offscreen = fit === "levels" || drawn.length === 0
      ? []
      : lines
          .filter((l) => l.value < Math.min(...drawn) - span
                      || l.value > Math.max(...drawn) + span)
          .map((l) => ({ key: l.key, text: t.chart.offscreen(l.label, f.toClose(l.value)) }));

    const levels = chart.levels
      ? [
          { label: t.chart.entry, value: f.premium(chart.levels.entry), tone: "text-ink" },
          { label: t.chart.target, value: f.toClose(chart.levels.target), tone: "text-pass" },
          { label: t.chart.stop, value: f.toClose(chart.levels.stop), tone: "text-fail" },
        ]
      : null;

    return {
      name: stripRoot(chart.name, chart.underlying),
      underlying: chart.underlying,
      // A line needs two points. One reading is a dot asserting nothing.
      drawable: series.length > 1,
      levels,
      nowTile: {
        label: t.chart.last,
        value: now === null ? t.common.dash : f.toClose(now),
        tone,
        note: now === null ? null : isLive ? t.chart.liveTag : t.chart.barTag,
        noteLive: isLive,
      } as Tile,
      pnlTile: {
        label: t.chart.pnl,
        value: pnl === null ? t.common.dash : f.money(pnl),
        tone: pnl === null ? "text-ink/40" : tone,
      } as Tile,
      pnl,
      // How far this position has come from its entry, and which way. The three level
      // tiles say where the boundaries are; none of them says whether the trade is
      // nearly over, which is the thing a person opening this screen wants first.
      progress: (() => {
        const p = exitProgress({
          entry: chart.levels ? Number(chart.levels.entry) : null,
          target: chart.levels ? Number(chart.levels.target) : null,
          stop: chart.levels ? Number(chart.levels.stop) : null,
          now: now === null ? null : Number(now),
        });
        if (!p) return null;
        const toward = p.toward === "target" ? t.chart.towardTarget
          : p.toward === "stop" ? t.chart.towardStop
          : t.chart.towardNeither;
        return {
          pct: p.pct,
          // The bar's own width, decided here so the markup does no arithmetic.
          width: `${p.pct}%`,
          label: p.toward === "neither" ? toward : t.chart.progressPct(p.pct, toward),
          note: p.beyond ? t.chart.progressBeyond : null,
          // Green toward the target, red toward the stop — the same pairing the level
          // tiles above already use, so the eye reads one language on this screen.
          tone: p.toward === "target" ? "bg-pass" : p.toward === "stop" ? "bg-fail" : "bg-ink/30",
        };
      })(),
      // Net delta and vega for this position alone. Three states, not two: figures,
      // "a leg has no greeks", or nothing at all before the marks route has answered.
      // The middle one is the one that matters — Alpaca omits greeks deep in or out of
      // the money and at 0DTE, and a flat-looking net is exactly the reading that
      // would stop somebody looking.
      greeks: !live?.greeks
        ? null
        : live.greeks.missing?.length
          ? { missing: t.chart.greeksMissing(live.greeks.missing.length), figures: null }
          : {
              missing: null,
              figures: [
                t.chart.netDelta(f.signed(live.greeks.delta ?? null, 0)),
                t.chart.netVega(f.signed(live.greeks.vega ?? null, 2)),
              ],
            },
      offscreen,
      forming: candles.some((c) => c.forming),
      // Offered from what the server actually serves, so the panel cannot drift from
      // the real set. AUTO matches the bar to the window.
      timeframes: [null, ...(chart.timeframes ?? [])].map<TimeframeChoice>((tf) => ({
        key: tf ?? "auto",
        label: tf ?? t.chart.auto,
        active: timeframe === tf,
        select: () => setTimeframe(tf),
      })),
      fitToLevels: fit === "levels",
      fitLabel: fit === "levels" ? t.chart.fitPrice : t.chart.fitLevels,
      legend: t.chart.legend(chart.policy.take_profit_pct, chart.policy.stop_loss_pct),
      forceClose: t.chart.forceClose(chart.policy.force_close_dte),
      kind: chart.levels?.credit ? t.chart.credit : t.chart.debit,
      footer: {
        opened: t.chart.openedAt(f.day(chart.opened_at), f.clock(chart.opened_at)),
        closed: chart.closed_at
          ? t.chart.closedAt(f.day(chart.closed_at), f.clock(chart.closed_at))
          : null,
        dte: chart.dte !== null && chart.open ? t.chart.dteTag(chart.dte) : null,
        // Coloured, because the line it sits on is grey and a loss printed grey reads
        // as a note rather than as a number. Same rule as the book.
        realized: chart.realized_usd
          ? { value: f.money(chart.realized_usd), negative: Number(chart.realized_usd) < 0 }
          : null,
      },
    };
  }, [chart, live, last, candles, lines, series, fit, timeframe, setTimeframe, t, f]);

  return { ...view, host, toggleFit, live: live as { legs?: LegMark[] } | undefined };
}
