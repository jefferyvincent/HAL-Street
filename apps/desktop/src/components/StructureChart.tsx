import { cn } from "@/lib/cn";
import { CLS } from "@/constants/theme";
import { LegTable } from "@/components/LegTable";
import { Ticker } from "@/components/Ticker";
import { Trend } from "@/components/Trend";
import { Note } from "@/components/Icon";
import { useStructureView, type Tile } from "@/hooks/useStructureView";
import { useStrings } from "@/hooks/useStrings";
import type { StructureChart as Chart } from "@/types";

/**
 * A structure's own price against the levels its exit policy acts on.
 *
 * The line is the *net* of the legs, on the same sign convention the exit uses:
 * negative means it is held for a credit. Entry, target and stop come from
 * `manager.exit_levels`, which a test pins to `evaluate_exit` — so the picture cannot
 * quietly disagree with what the agent will actually do.
 *
 * Everything it says is worked out in `useStructureView`; this is the frame.
 */
export function StructureChart({ chart, error }: { chart: Chart; error: string | null }) {
  const t = useStrings();
  const view = useStructureView(chart);

  return (
    <>
      {/* Which underlying, from the chart's own field. A structure opened before
          names carried a ticker has none, and this view is where someone decides
          what a position is doing — the least good place to have to infer it. */}
      <div className="mb-2 flex items-baseline gap-[9px]">
        <Ticker symbol={view.underlying} size="md" />
        <span className="min-w-0 font-mono text-[12px] font-semibold leading-[1.3] text-ink">
          {view.name}
        </span>
      </div>

      <div className="mb-3 grid grid-cols-2 gap-px bg-line min-[701px]:grid-cols-3 min-[961px]:grid-cols-5">
        {view.levels ? (
          view.levels.map((level) => <Level key={level.label} tile={level} />)
        ) : (
          <div className="col-span-2 min-[961px]:col-span-3 bg-void px-[10px] py-[9px] font-sans text-[11.5px] leading-[1.5] text-ink/40">
            {t.chart.noEntry}
          </div>
        )}
        {/* Coloured by whether the position is winning, not by the price's own
            sign — every credit structure marks negative, so a sign-based colour
            would paint them all red for the whole of their life. */}
        <Level tile={view.nowTile} />
        <Level tile={view.pnlTile} lead={<Trend value={view.pnl} size={10} />} />
      </div>

      {view.drawable ? (
        <div ref={view.host} className="h-[320px] w-full border border-line bg-panel" />
      ) : (
        <div className={cn(CLS.empty, "border border-line bg-panel")}>
          {error ?? t.chart.noHistory}
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[9.5px] leading-[1.4] text-ink/40">
        <span className="flex items-center gap-[6px]" title={t.chart.timeframeTitle}>
          {view.timeframes.map((tf) => (
            <button
              key={tf.key}
              onClick={tf.select}
              aria-pressed={tf.active}
              className={cn("font-mono text-[9.5px] font-bold leading-none tracking-[.06em]",
                "transition-colors hover:text-ink focus-visible:outline",
                "focus-visible:outline-1 focus-visible:outline-amber",
                tf.active ? "text-amber" : "text-ink/35")}>
              {tf.label}
            </button>
          ))}
        </span>

        <button
          onClick={view.toggleFit}
          title={t.chart.fitTitle}
          aria-pressed={view.fitToLevels}
          className={cn("font-mono text-[9.5px] font-bold leading-none tracking-[.08em]",
            "transition-colors hover:text-ink focus-visible:outline focus-visible:outline-1",
            "focus-visible:outline-amber",
            view.fitToLevels ? "text-amber" : "text-ink/45")}>
          {view.fitLabel}
        </button>
        <span>{view.legend}</span>
        <span>{view.forceClose}</span>
        <span>{view.kind}</span>
        <span>{t.chart.seriesNote}</span>
        {view.forming && <span className="text-amber/70">{t.chart.forming}</span>}
        {/* A level outside the drawn range is invisible and silent otherwise — the
            reader has no way to tell "no stop" from "stop somewhere below". Naming
            it, with the way to see it, is the price of not scaling to it. */}
        {view.offscreen.map((l) => (
          <span key={l.key} className="text-ink/35">{l.text}</span>
        ))}
      </div>

      <LegTable chart={chart} live={view.live} />

      <div className="mt-2 font-mono text-[9.5px] leading-[1.4] text-ink/35">
        {view.footer.opened}
        {view.footer.closed && <>{t.common.sep}{view.footer.closed}</>}
        {view.footer.dte && <>{t.common.sep}{view.footer.dte}</>}
        {view.footer.realized && (
          <>{t.common.sep}{t.chart.realizedTag}{" "}
            <span className={view.footer.realized.negative ? "text-fail" : "text-pass"}>
              {view.footer.realized.value}
            </span>
          </>
        )}
      </div>

      <Note>{t.chart.note}</Note>
    </>
  );
}

/** One figure with its label, and the note that says how old it is. */
function Level({ tile, lead = null }: { tile: Tile; lead?: React.ReactNode }) {
  return (
    <div className="flex-1 border border-line bg-void px-[10px] py-[9px]">
      <div className="font-mono text-[8.5px] font-bold leading-none tracking-[.08em] text-ink/40">
        {tile.label}
      </div>
      <div className={cn("mt-[5px] flex items-center gap-[5px] font-mono text-[13px] font-semibold leading-none tabular-nums", tile.tone)}>
        {lead}
        {tile.value}
      </div>
      {tile.note && (
        <div className={cn("mt-[4px] font-mono text-[9px] leading-none",
          tile.noteLive ? "text-pass/70" : "text-ink/30")}>
          {tile.note}
        </div>
      )}
    </div>
  );
}
