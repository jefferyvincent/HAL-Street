import { cn } from "@/lib/cn";
import { CLS } from "@/constants/theme";
import { LegTable } from "@/components/LegTable";
import { Ticker } from "@/components/Ticker";
import { Trend } from "@/components/Trend";
import { money, toClose } from "@/lib/format";
import { useMarks } from "@/hooks/useMarks";
import { useStrings } from "@/hooks/useStrings";
import type { BookRow } from "@/hooks/useBook";

/**
 * What a position looks like while its price history is on the way.
 *
 * The chart route spawns an MCP subprocess and waits on Alpaca — about seven hundred
 * milliseconds, and again on every change of bar size. The whole view used to
 * collapse to one line of text for that long: the header, the levels, the legs and
 * the canvas all replaced by "fetching price history…". A layout that empties itself
 * reads as broken rather than as busy, and the reader loses their place.
 *
 * Almost none of that waiting was necessary. The name, the ticker, the size, the
 * legs, their fills, their live prices and the position's P&L are already on the
 * panel before anyone clicks — they arrive on the snapshot and the marks route, and
 * both have long since answered. Spinning over information in hand is the thing to
 * avoid; the only genuinely unknown parts are the price history and the two policy
 * levels derived from it.
 *
 * So this is the real view with two holes in it, not a placeholder for the view.
 * Same geometry throughout, so nothing moves when the data lands.
 */
export function ChartPending({ row }: { row: BookRow }) {
  const t = useStrings();
  const live = useMarks()?.marks[row.structureId];
  const mark = live?.mark ?? null;
  const pnl = live?.unrealized_usd ?? row.unrealized ?? null;

  return (
    <>
      <div className="mb-2 flex items-baseline gap-[9px]">
        <Ticker symbol={row.underlying} size="md" />
        <span className="min-w-0 font-mono text-[12px] font-semibold leading-[1.3] text-ink">
          {row.name.startsWith(`${row.underlying} `)
            ? row.name.slice(row.underlying.length + 1)
            : row.name}
        </span>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-px bg-line min-[701px]:grid-cols-3 min-[961px]:grid-cols-5">
        {/* Known from the ledger the moment the panel loaded. */}
        <Tile label={t.chart.entry}
              value={row.entry ? toClose(row.entry) : null} tone="text-ink" />
        {/* Not known: both are derived from the exit policy by the same function the
            agent acts on, and asking the panel to compute them would be the one way
            this picture could come to disagree with what the agent will do. */}
        <Tile label={t.chart.target} value={null} tone="text-pass" />
        <Tile label={t.chart.stop} value={null} tone="text-fail" />
        {/* Known from the marks route, which answered before the click. */}
        <Tile label={t.chart.last}
              value={mark === null ? null : toClose(mark)}
              tone={pnl === null ? "text-ink" : Number(pnl) >= 0 ? "text-pass" : "text-fail"} />
        <Tile label={t.chart.pnl}
              value={pnl === null ? null : money(pnl)}
              tone={pnl === null ? "text-ink/40" : Number(pnl) >= 0 ? "text-pass" : "text-fail"}
              lead={pnl === null ? null : <Trend value={Number(pnl)} size={10} />} />
      </div>

      {/* The one real hole, at the height the chart will occupy — so the page does
          not jump when it lands. */}
      <div className={cn("flex h-[320px] w-full items-center justify-center",
        "border border-line bg-panel")}>
        <div className="flex flex-col items-center gap-[10px]">
          <div className="shimmer h-[3px] w-[140px] bg-line" />
          <span className="font-mono text-[9.5px] leading-none tracking-[.08em] text-ink/30">
            {t.chart.loading}
          </span>
        </div>
      </div>

      <div className={cn(CLS.empty, "px-0 py-2 text-[9.5px] text-ink/25")}>
        {t.chart.loadingNote}
      </div>

      {/* Fully rendered from the marks, which carry the recorded fill beside the live
          mid. There is nothing here to wait for. */}
      <LegTable chart={null} live={live} />
    </>
  );
}

function Tile({ label, value, tone, lead = null }: {
  label: string; value: string | null; tone: string; lead?: React.ReactNode;
}) {
  return (
    <div className="border border-line bg-void px-[10px] py-[9px]">
      <div className="font-mono text-[8.5px] font-bold leading-none tracking-[.08em] text-ink/40">
        {label}
      </div>
      <div className={cn("mt-[5px] flex h-[13px] items-center gap-[5px] font-mono text-[13px] font-semibold leading-none tabular-nums", tone)}>
        {value === null
          ? <span className="shimmer h-[9px] w-[62px] bg-line" />
          : <>{lead}{value}</>}
      </div>
    </div>
  );
}
