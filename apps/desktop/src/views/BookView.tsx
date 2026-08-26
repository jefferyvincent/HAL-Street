import { cn } from "@/lib/cn";
import { day, money } from "@/lib/format";
import { ICON } from "@/constants/icons";
import { CLS } from "@/constants/theme";
import { Icon, Note } from "@/components/Icon";
import { StructureChart } from "@/components/StructureChart";
import { useBook } from "@/hooks/useBook";
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
  const charting = useUI((s) => s.charting);
  const chartFor = useUI((s) => s.chart);
  const { chart, loading, error } = useStructureChart(charting);
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
        loading ? (
          <div className={cn(CLS.empty, "border border-line bg-panel")}>{t.chart.loading}</div>
        ) : chart ? (
          <StructureChart chart={chart} error={error} />
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
                    <td className={cn(CLS.td, "text-ink")}>{r.name}</td>
                    <td className={CLS.td}>{r.underlying}</td>
                    <td className={cn(CLS.td, "tabular-nums")}>{r.qty}</td>
                    <td className={cn(CLS.td, "whitespace-nowrap tabular-nums")}>
                      {r.entry ? money(r.entry) : "—"}
                    </td>
                    <td className={cn(CLS.td, "whitespace-nowrap tabular-nums")}>
                      {r.exit ? money(r.exit) : "—"}
                    </td>
                    <td className={cn(CLS.td, "whitespace-nowrap tabular-nums")}>
                      {r.realized ? (
                        <span className={Number(r.realized) < 0 ? "text-fail" : "text-pass"}>
                          {money(r.realized)}
                        </span>
                      ) : (
                        <span className="text-ink/32">{day(r.openedAt)}</span>
                      )}
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
