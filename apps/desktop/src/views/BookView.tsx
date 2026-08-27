import { cn } from "@/lib/cn";
import { day, money, premium } from "@/lib/format";
import { ICON } from "@/constants/icons";
import { CLS } from "@/constants/theme";
import { Icon, Note } from "@/components/Icon";
import { ChartPending } from "@/components/ChartPending";
import { StructureChart } from "@/components/StructureChart";
import { PatternBadge } from "@/components/PatternBadge";
import { Ticker } from "@/components/Ticker";
import { Trend } from "@/components/Trend";
import { useBook, type BookRow } from "@/hooks/useBook";
import { useMarks } from "@/hooks/useMarks";
import { useStructureChart } from "@/hooks/useStructureChart";
import { useStrings } from "@/hooks/useStrings";
import { useUI } from "@/stores/ui";

/**
 * Every structure the agent has held, and the chart for whichever one is open.
 *
 * One view rather than two: the list is how you get to a chart, and a chart with no
 * way back to the list is a dead end. Clicking a row swaps the table for the chart;
 * the header's back control swaps it back.
 */
export function BookView() {
  const t = useStrings();
  const { rows, open, closed } = useBook();
  // The same source the console's holding card reads, so the two cannot disagree
  // about what a position is worth.
  const live = useMarks();
  const charting = useUI((s) => s.charting);
  const chartFor = useUI((s) => s.chart);
  const timeframe = useUI((s) => s.chartTimeframe);
  const { chart, loading, error } = useStructureChart(charting, timeframe);
  const col = t.book.columns;

  const showing = rows.find((r) => r.structureId === charting);

  return (
    <>
      <div className={CLS.heading}>
        {charting ? (
          <button onClick={() => chartFor(null)}
                  className="flex cursor-pointer items-center gap-[6px] text-ink/60 hover:text-ink">
            <Icon d={ICON.back} size={12} stroke="currentColor" />
            {t.chart.back}
          </button>
        ) : (
          t.book.title
        )}
        <span className="flex-1" />
        <span className={CLS.headingMeta}>
          {charting && showing ? showing.name : t.book.meta(open, closed)}
        </span>
      </div>

      {charting ? (
        // The whole view used to collapse to one line of text for the ~700ms the
        // chart route takes, and again on every change of bar size. Almost none of
        // that wait was necessary: the name, size, legs, fills, live prices and P&L
        // are all on the panel before the click. `ChartPending` is the real view with
        // two holes in it — same geometry, so nothing moves when the data lands.
        loading && showing ? (
          <ChartPending row={showing} />
        ) : loading ? (
          <div className={cn(CLS.empty, "border border-line bg-panel")}>{t.chart.loading}</div>
        ) : chart ? (
          // Keyed, so a bar-size change builds a new canvas rather than reusing one
          // that still holds the old chart's zoom, scroll and price-scale override.
          // The loading branch above already unmounts it today; this makes that a
          // property of the code rather than a consequence of how the fetch renders.
          <StructureChart key={`${charting}:${timeframe ?? "auto"}`}
                          chart={chart} error={error} />
        ) : (
          <div className={cn(CLS.empty, "border border-line bg-panel")}>{error}</div>
        )
      ) : rows.length === 0 ? (
        <div className={CLS.empty}>{t.book.empty}</div>
      ) : (
        <>
          <div className="w-full overflow-x-auto border border-line bg-panel">
            <table className="w-full">
              <thead>
                <tr>
                  {[col.status, col.structure, col.underlying, col.qty,
                    col.entry, col.exit, col.realized].map((c) => (
                    <th key={c} className={CLS.th}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.structureId}
                      onClick={() => chartFor(r.structureId)}
                      className="cursor-pointer hover:bg-panel">
                    <td className={CLS.td}>
                      <span className={cn("whitespace-nowrap font-mono text-[10px] font-bold leading-none tracking-[.08em]",
                        r.open ? "text-amber" : "text-ink/45")}>
                        {r.open ? t.book.open : t.book.closed}
                      </span>
                    </td>
                    <td className={cn(CLS.td, "text-ink")}>
                      {r.name}
                      {/* Moved here off the P&L column, which it had no business
                          occupying — see below. */}
                      <div className="mt-[3px] font-mono text-[9.5px] leading-none text-ink/30">
                        {day(r.openedAt)}
                      </div>
                      {/* Only for what is still on. A chart read beside a closed
                          position describes a risk nobody is carrying. */}
                      {r.position && (
                        <div className="mt-[5px]">
                          <PatternBadge position={r.position} />
                        </div>
                      )}
                    </td>
                    <td className={CLS.td}><Ticker symbol={r.underlying} /></td>
                    <td className={cn(CLS.td, "tabular-nums")}>{r.qty}</td>
                    <td className={cn(CLS.td, "whitespace-nowrap tabular-nums")}>
                      {r.entry ? premium(r.entry) : "—"}
                    </td>
                    <td className={cn(CLS.td, "whitespace-nowrap tabular-nums")}>
                      {r.exit ? premium(r.exit) : "—"}
                    </td>
                    {/* Realized on a closed row, marked-to-market on an open one.
                        This column was REALIZED, which an open position does not
                        have — so a live spread down nineteen dollars showed a grey
                        open-date here, and the column that says P&L was the one place
                        the book would not tell you the P&L. */}
                    <td className={cn(CLS.td, "whitespace-nowrap tabular-nums")}>
                      <Pnl row={r} live={live?.marks[r.structureId]?.unrealized_usd} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Note>{t.book.note}</Note>
        </>
      )}
    </>
  );
}

/**
 * One row's P&L: realized once closed, marked-to-market while open.
 *
 * Both are money made or lost on the same position and belong in one column. What
 * they are not is interchangeable, so the open one is tagged — a number that can
 * still move is a different claim from one that cannot.
 *
 * Live where the broker answered, the agent's own last read otherwise, and nothing
 * at all when neither can price it. A structure with a missing quote is unpriceable,
 * not flat, and printing $0.00 there would be the worst of the three.
 */
function Pnl({ row, live }: { row: BookRow; live?: string | null }) {
  const t = useStrings();
  const value = row.open ? live ?? row.unrealized : row.realized;
  if (value === null || value === undefined) {
    return <span className="text-ink/32">{t.book.unpriced}</span>;
  }
  const n = Number(value);
  if (!Number.isFinite(n)) {
    return <span className="text-ink/32">{t.book.unpriced}</span>;
  }
  return (
    <span className="flex items-center gap-[5px]">
      <Trend value={n} size={10} />
      <span className={n < 0 ? "text-fail" : "text-pass"}>{money(value)}</span>
      {row.open && (
        <span className="font-mono text-[9px] leading-none text-ink/30">
          {t.book.unrealizedTag}
        </span>
      )}
    </span>
  );
}
