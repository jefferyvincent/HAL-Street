import { cn } from "@/lib/cn";
import { clock, day, money, premium, toClose } from "@/lib/format";
import { CLS } from "@/constants/theme";
import { useStructureChartCanvas } from "@/hooks/useStructureChartCanvas";
import { useStructureLevels } from "@/hooks/useStructureLevels";
import { useStrings } from "@/hooks/useStrings";
import type { StructureChart as Chart } from "@/types";
import { Note } from "./Icon";

function Level({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="flex-1 border border-line bg-void px-[10px] py-[9px]">
      <div className="font-mono text-[8.5px] font-bold leading-none tracking-[.08em] text-ink/40">
        {label}
      </div>
      <div className={cn("mt-[5px] font-mono text-[13px] font-semibold leading-none tabular-nums", tone)}>
        {value}
      </div>
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
  const { series, lines, last } = useStructureLevels(chart);
  const host = useStructureChartCanvas(series, lines);
  const levels = chart.levels;

  return (
    <>
      {/* Which underlying, from the chart's own field. A structure opened before
          names carried a ticker has none, and this view is where someone decides
          what a position is doing — the least good place to have to infer it. */}
      <div className="mb-2 flex items-baseline gap-[9px]">
        <span className="font-mono text-[13px] font-bold leading-none text-amber">
          {chart.underlying}
        </span>
        <span className="min-w-0 font-mono text-[12px] font-semibold leading-[1.3] text-ink">
          {chart.name.startsWith(`${chart.underlying} `)
            ? chart.name.slice(chart.underlying.length + 1)
            : chart.name}
        </span>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-px bg-line min-[701px]:grid-cols-4">
        {levels ? (
          <>
            <Level label={t.chart.entry} value={premium(levels.entry)} tone="text-ink" />
            <Level label={t.chart.target} value={toClose(levels.target)} tone="text-pass" />
            <Level label={t.chart.stop} value={toClose(levels.stop)} tone="text-fail" />
          </>
        ) : (
          <div className="col-span-3 bg-void px-[10px] py-[9px] font-sans text-[11.5px] leading-[1.5] text-ink/40">
            {t.chart.noEntry}
          </div>
        )}
        <Level
          label={t.chart.last}
          value={last === null ? "—" : toClose(last)}
          tone={levels && last !== null && last >= Number(levels.target) ? "text-pass" : "text-ink"}
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
        <span>{t.chart.legend(chart.policy.take_profit_pct, chart.policy.stop_loss_pct)}</span>
        <span>{t.chart.forceClose(chart.policy.force_close_dte)}</span>
        <span>{levels?.credit ? t.chart.credit : t.chart.debit}</span>
      </div>

      <div className="mt-3 border border-line bg-panel">
        {chart.legs.map((leg) => (
          <div key={leg.symbol}
               className="flex items-center gap-[9px] border-b border-line-soft px-3 py-[7px] last:border-b-0">
            <span className={cn("w-[34px] font-mono text-[10px] font-bold leading-none",
              leg.signed < 0 ? "text-fail" : "text-pass")}>
              {leg.signed > 0 ? `+${leg.signed}` : leg.signed}
            </span>
            <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] leading-[1.2] text-ink">
              {leg.symbol}
            </span>
          </div>
        ))}
      </div>

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
