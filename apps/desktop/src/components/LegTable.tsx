import { cn } from "@/lib/cn";
import { money, plain } from "@/lib/format";
import { legRows } from "@/lib/legRows";
import { useStrings } from "@/hooks/useStrings";
import { Note } from "@/components/Icon";
import type { LegMark, StructureChart as Chart } from "@/types";

/**
 * Every leg of a structure, with what it filled at and what it has done since.
 *
 * "The spread is ten dollars down" invites exactly one follow-up question, and until
 * the opening order's per-leg fills were kept there was nothing in this system that
 * could answer it — the ledger recorded the net and discarded the rest.
 *
 * Two sources, merged by `legRows` and neither recomputed here. The fills come off
 * the order and never change; the marks come from the same `mark_legs` the net is
 * summed from. So a leg shown as unpriced is a leg the net is refusing to include,
 * and the P&L column adds to the figure in the tile above it exactly rather than
 * approximately.
 *
 * `chart` may be null. That is not an error state — it is the second between opening
 * a position and its history arriving, and the marks alone can fill this table.
 * Rendering it then beats spinning over information already in hand.
 */
export function LegTable({ chart, live }: {
  chart: Chart | null;
  live: { legs?: LegMark[] } | null | undefined;
}) {
  const t = useStrings();
  const rows = legRows(chart, live);
  const closed = chart ? !chart.open : false;
  // Only for a position still on. A structure opened before per-leg fills were kept
  // has no basis to show and no way to get one — the order is long since filled, and
  // the backfill only runs while it is held.
  const pending = !closed && rows.length > 0 && rows.every((r) => r.basis === null);

  if (rows.length === 0) return null;

  return (
    <div className="mt-3">
      <div className="flex items-center gap-2 border border-b-0 border-line bg-panel px-3 py-[7px]">
        <span className="font-mono text-[9px] font-bold leading-none tracking-[.12em] text-ink/50">
          {t.chart.legs}
        </span>
        <span className="flex-1" />
        <Head className="w-[74px]">{t.chart.legFill}</Head>
        <Head className="w-[74px]">{closed ? t.chart.exitAt : t.chart.legNow}</Head>
        <Head className="w-[86px]">{t.chart.legPnl}</Head>
      </div>

      <div className="border border-line bg-panel">
        {rows.map((leg) => {
          const pnl = leg.pnl === null ? null : Number(leg.pnl);
          const short = leg.contracts < 0;
          return (
            <div key={leg.symbol}
                 className="flex items-center gap-2 border-b border-line-soft px-3 py-[7px] last:border-b-0">
              {/* Signed contracts after size, so a two-lot reads as the two lots the
                  account is actually holding rather than as the one-spread ratio. */}
              <span className={cn("w-[34px] shrink-0 font-mono text-[10px] font-bold leading-none tabular-nums",
                short ? "text-fail" : "text-pass")}
                    title={short ? t.chart.legShort : t.chart.legLong}>
                {leg.contracts > 0 ? `+${leg.contracts}` : leg.contracts}
              </span>
              <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] leading-[1.2] text-ink">
                {leg.symbol}
              </span>
              <Cell className="w-[74px]">
                {leg.basis === null
                  ? <span className="text-ink/25">{t.chart.legNoBasis}</span>
                  : plain(leg.basis)}
              </Cell>
              <Cell className="w-[74px]">
                {leg.now === null
                  ? <span className="text-ink/25">{t.chart.legNoQuote}</span>
                  : plain(leg.now)}
              </Cell>
              <Cell className={cn("w-[86px] font-semibold",
                pnl === null || !Number.isFinite(pnl) ? "text-ink/25"
                : pnl >= 0 ? "text-pass" : "text-fail")}>
                {pnl === null || !Number.isFinite(pnl) ? "\u2014" : money(pnl)}
              </Cell>
            </div>
          );
        })}
      </div>

      {pending && <Note>{t.chart.legsPending}</Note>}
      <Note>{t.chart.legsNote}</Note>
    </div>
  );
}

/** A column heading, sized to match the cell beneath it so the two stay aligned. */
function Head({ children, className }: { children: React.ReactNode; className: string }) {
  return (
    <span className={cn("shrink-0 text-right font-mono text-[8.5px] font-bold",
      "leading-none tracking-[.08em] text-ink/35", className)}>
      {children}
    </span>
  );
}

function Cell({ children, className }: { children: React.ReactNode; className: string }) {
  return (
    <span className={cn("shrink-0 text-right font-mono text-[11px] leading-none tabular-nums text-ink/75",
      className)}>
      {children}
    </span>
  );
}
