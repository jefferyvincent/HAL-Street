import { cn } from "@/lib/cn";
import { Ticker } from "@/components/Ticker";
import { CLS } from "@/constants/theme";
import { Note } from "@/components/Icon";
import { useJournal } from "@/hooks/useJournal";
import { useStrings } from "@/hooks/useStrings";

/**
 * Every decision, with room for the whole rejection reason.
 *
 * The tape down the right of the console is one column wide and truncates; this is
 * the same records at full width. A row opens the decision record — which is the
 * console — so the two are one navigation rather than two copies of the data.
 */
export function JournalView() {
  const t = useStrings();
  const { lines, open } = useJournal();
  const col = t.journal.columns;

  return (
    <>
      <div className={CLS.heading}>
        {t.journal.title}
        <span className="flex-1" />
        <span className={CLS.headingMeta}>{t.journal.meta(lines.length)}</span>
      </div>

      {lines.length === 0 ? (
        <div className={CLS.empty}>{t.journal.empty}</div>
      ) : (
        <div className="w-full overflow-x-auto border border-line bg-panel">
          <table className="w-full">
            <thead>
              <tr>
                {[col.time, col.verdict, col.underlying, col.structure, col.gates, col.failedOn].map((c) => (
                  <th key={c} className={CLS.th}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {lines.map((r) => (
                <tr
                  key={r.ts}
                  onClick={() => open(r.ts)}
                  className={cn("cursor-pointer", r.selected ? "bg-panel" : "hover:bg-panel")}
                >
                  <td className={cn(CLS.td, "whitespace-nowrap tabular-nums text-ink/45")}>
                    <span className="text-ink/32">{r.day}</span> {r.time}
                  </td>
                  <td className={CLS.td}>
                    <span className={cn("whitespace-nowrap font-mono text-[10px] font-bold leading-none tracking-[.08em]",
                      r.approved ? "text-pass" : "text-fail")}>
                      {r.verdict}
                    </span>
                  </td>
                  <td className={CLS.td}>
                    {r.underlying ? <Ticker symbol={r.underlying} /> : t.common.dash}
                  </td>
                  <td className={cn(CLS.td, "text-ink")}>{r.structure}</td>
                  <td className={cn(CLS.td, "whitespace-nowrap tabular-nums")}>{r.gates}</td>
                  <td className={CLS.td}>
                    {r.failed ? (
                      <span className="text-fail-ink">{r.failed}</span>
                    ) : (
                      <span className="text-ink/32">{t.common.dash}</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Note>{t.journal.note}</Note>
    </>
  );
}
