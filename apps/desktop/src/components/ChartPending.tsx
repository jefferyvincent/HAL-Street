import { cn } from "@/lib/cn";
import { CLS } from "@/constants/theme";
import { LegTable } from "@/components/LegTable";
import { Ticker } from "@/components/Ticker";
import { Trend } from "@/components/Trend";
import { useChartPending, type PendingTile } from "@/hooks/useChartPending";
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
 * So this is the real view with two holes in it, not a placeholder for the view.
 * Same geometry throughout, so nothing moves when the data lands. Which parts are
 * holes is decided in `useChartPending`.
 */
export function ChartPending({ row }: { row: BookRow }) {
  const t = useStrings();
  const { name, underlying, tiles, live } = useChartPending(row);

  return (
    <>
      <div className="mb-2 flex items-baseline gap-[9px]">
        <Ticker symbol={underlying} size="md" />
        <span className="min-w-0 font-mono text-[12px] font-semibold leading-[1.3] text-ink">
          {name}
        </span>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-px bg-line min-[701px]:grid-cols-3 min-[961px]:grid-cols-5">
        {tiles.map((tile) => <Tile key={tile.label} tile={tile} />)}
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

function Tile({ tile }: { tile: PendingTile }) {
  return (
    <div className="border border-line bg-void px-[10px] py-[9px]">
      <div className="font-mono text-[8.5px] font-bold leading-none tracking-[.08em] text-ink/40">
        {tile.label}
      </div>
      <div className={cn("mt-[5px] flex h-[13px] items-center gap-[5px] font-mono text-[13px] font-semibold leading-none tabular-nums", tile.tone)}>
        {tile.value === null
          ? <span className="shimmer h-[9px] w-[62px] bg-line" />
          : <>{tile.trend !== null && <Trend value={tile.trend} size={10} />}{tile.value}</>}
      </div>
    </div>
  );
}
