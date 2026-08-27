import { cn } from "@/lib/cn";
import { LegTable } from "@/components/LegTable";
import { Ticker } from "@/components/Ticker";
import { Trend } from "@/components/Trend";
import { clock, day, money, premium, toClose } from "@/lib/format";
import { CLS } from "@/constants/theme";
import { useStructureChartCanvas } from "@/hooks/useStructureChartCanvas";
import { useMarks } from "@/hooks/useMarks";
import { useUI } from "@/stores/ui";
import { useStructureLevels } from "@/hooks/useStructureLevels";
import { useStrings } from "@/hooks/useStrings";
import type { StructureChart as Chart } from "@/types";
import { Note } from "./Icon";

function Level({ label, value, tone, note = null, lead = null }: {
  label: string; value: string; tone: string; note?: string | null;
  lead?: React.ReactNode;
}) {
  return (
    <div className="flex-1 border border-line bg-void px-[10px] py-[9px]">
      <div className="font-mono text-[8.5px] font-bold leading-none tracking-[.08em] text-ink/40">
        {label}
      </div>
      <div className={cn("mt-[5px] flex items-center gap-[5px] font-mono text-[13px] font-semibold leading-none tabular-nums", tone)}>
        {lead}
        {value}
      </div>
      {note && (
        <div className={cn("mt-[4px] font-mono text-[9px] leading-none",
          note === "live" ? "text-pass/70" : "text-ink/30")}>
          {note}
        </div>
      )}
    </div>
  );
}

/**
 * A structure's own price against the levels its exit policy acts on.
 *
 * The line is the *net* of the legs, on the same sign convention the exit uses:
 * negative means it is held for a credit. Entry, target and stop come from
 * `manager.exit_levels`, which a test pins to `evaluate_exit` — so the picture cannot
 * quietly disagree with what the agent will actually do.
 */
export function StructureChart({ chart, error }: { chart: Chart; error: string | null }) {
  const t = useStrings();
  const levels = chart.levels;

  // NOW should be a price, not the close of an hour that may be nearly over. The
  // series is hourly bars — right for the line, wrong for "what is it worth" — so
  // the live mark leads and the last bar stands in when the broker cannot be
  // reached. Labelled either way: a number whose age is unknown is worth less than
  // a stale one that says so.
  const live = useMarks()?.marks[chart.structure_id];
  const mark = live?.mark == null ? null : Number(live.mark);
  const { series, candles, lines, last } = useStructureLevels(chart, mark);
  const fit = useUI((s) => s.chartFit);
  const toggleFit = useUI((s) => s.toggleFit);
  const timeframe = useUI((s) => s.chartTimeframe);
  const setTimeframe = useUI((s) => s.setTimeframe);
  const host = useStructureChartCanvas(series, candles, lines, mark, fit);
  const now = live?.mark ?? (last === null ? null : String(last));
  const isLive = live?.mark != null;
  const pnl = live?.unrealized_usd ?? null;

  // Which levels the drawn range does not reach. Only meaningful when scaled to the
  // price — asking to fit them is what makes them visible, so under that scale there
  // is nothing to report.
  const drawn = candles.flatMap((c) => [c.high, c.low]);
  const span = drawn.length ? Math.max(...drawn) - Math.min(...drawn) || 0.1 : 0;
  const offscreen = fit === "levels" || drawn.length === 0 ? [] : lines.filter(
    (l) => l.value < Math.min(...drawn) - span || l.value > Math.max(...drawn) + span);

  return (
    <>
      {/* Which underlying, from the chart's own field. A structure opened before
          names carried a ticker has none, and this view is where someone decides
          what a position is doing — the least good place to have to infer it. */}
      <div className="mb-2 flex items-baseline gap-[9px]">
        <Ticker symbol={chart.underlying} size="md" />
        <span className="min-w-0 font-mono text-[12px] font-semibold leading-[1.3] text-ink">
          {chart.name.startsWith(`${chart.underlying} `)
            ? chart.name.slice(chart.underlying.length + 1)
            : chart.name}
        </span>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-px bg-line min-[701px]:grid-cols-3 min-[961px]:grid-cols-5">
        {levels ? (
          <>
            <Level label={t.chart.entry} value={premium(levels.entry)} tone="text-ink" />
            <Level label={t.chart.target} value={toClose(levels.target)} tone="text-pass" />
            <Level label={t.chart.stop} value={toClose(levels.stop)} tone="text-fail" />
          </>
        ) : (
          <div className="col-span-2 min-[961px]:col-span-3 bg-void px-[10px] py-[9px] font-sans text-[11.5px] leading-[1.5] text-ink/40">
            {t.chart.noEntry}
          </div>
        )}
        {/* Coloured by whether the position is winning, not by the price's own
            sign — every credit structure marks negative, so a sign-based colour
            would paint them all red for the whole of their life. */}
        <Level
          label={t.chart.last}
          value={now === null ? "—" : toClose(now)}
          tone={pnl === null ? "text-ink"
                : Number(pnl) >= 0 ? "text-pass" : "text-fail"}
          note={now === null ? null : isLive ? t.chart.liveTag : t.chart.barTag}
        />
        <Level
          label={t.chart.pnl}
          value={pnl === null ? "—" : money(pnl)}
          tone={pnl === null ? "text-ink/40" : Number(pnl) >= 0 ? "text-pass" : "text-fail"}
          lead={<Trend value={pnl} size={10} />}
        />
      </div>

      {series.length > 1 ? (
        <div ref={host} className="h-[320px] w-full border border-line bg-panel" />
      ) : (
        <div className={cn(CLS.empty, "border border-line bg-panel")}>
          {error ?? t.chart.noHistory}
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[9.5px] leading-[1.4] text-ink/40">
        {/* Offered from what the server actually serves, so the panel cannot drift
            from the real set. AUTO matches the bar to the window, which is what
            this did before it was selectable. */}
        <span className="flex items-center gap-[6px]" title={t.chart.timeframeTitle}>
          {[null, ...(chart.timeframes ?? [])].map((tf) => (
            <button
              key={tf ?? "auto"}
              onClick={() => setTimeframe(tf)}
              aria-pressed={timeframe === tf}
              className={cn("font-mono text-[9.5px] font-bold leading-none tracking-[.06em]",
                "transition-colors hover:text-ink focus-visible:outline",
                "focus-visible:outline-1 focus-visible:outline-amber",
                timeframe === tf ? "text-amber" : "text-ink/35")}>
              {tf ?? t.chart.auto}
            </button>
          ))}
        </span>

        <button
          onClick={toggleFit}
          title={t.chart.fitTitle}
          aria-pressed={fit === "levels"}
          className={cn("font-mono text-[9.5px] font-bold leading-none tracking-[.08em]",
            "transition-colors hover:text-ink focus-visible:outline focus-visible:outline-1",
            "focus-visible:outline-amber",
            fit === "levels" ? "text-amber" : "text-ink/45")}>
          {fit === "levels" ? t.chart.fitPrice : t.chart.fitLevels}
        </button>
        <span>{t.chart.legend(chart.policy.take_profit_pct, chart.policy.stop_loss_pct)}</span>
        <span>{t.chart.forceClose(chart.policy.force_close_dte)}</span>
        <span>{levels?.credit ? t.chart.credit : t.chart.debit}</span>
        <span>{t.chart.seriesNote}</span>
        {candles.some((c) => c.forming) && (
          <span className="text-amber/70">{t.chart.forming}</span>
        )}
        {/* A level outside the drawn range is invisible and silent otherwise — the
            reader has no way to tell "no stop" from "stop somewhere below". Naming
            it, with the way to see it, is the price of not scaling to it. */}
        {offscreen.map((l) => (
          <span key={l.key} className="text-ink/35">
            {t.chart.offscreen(l.label, toClose(l.value))}
          </span>
        ))}
      </div>

      <LegTable chart={chart} live={live} />

      <div className="mt-2 font-mono text-[9.5px] leading-[1.4] text-ink/35">
        opened {day(chart.opened_at)} {clock(chart.opened_at)}
        {chart.closed_at && <> · closed {day(chart.closed_at)} {clock(chart.closed_at)}</>}
        {chart.dte !== null && chart.open && <> · {chart.dte} DTE</>}
        {chart.realized_usd && <> · realized {money(chart.realized_usd)}</>}
      </div>

      <Note>{t.chart.note}</Note>
    </>
  );
}
