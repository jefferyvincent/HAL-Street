import { cn } from "@/lib/cn";
import { Ticker } from "@/components/Ticker";
import { clock, day } from "@/lib/format";
import { CLS } from "@/constants/theme";
import { Note } from "@/components/Icon";
import { useDecisions } from "@/hooks/useDecisions";
import { useStrings } from "@/hooks/useStrings";
import { useUI } from "@/stores/ui";

/**
 * Every decision, with room for the whole rejection reason.
 *
 * The tape down the right of the console is one column wide and truncates; this is
 * the same records at full width. A row opens the decision record — which is the
 * console — so the two are one navigation rather than two copies of the data.
 */
export function JournalView() {
  const t = useStrings();
  const { rows, selected } = useDecisions();
  const open = useUI((s) => s.open);
  const col = t.journal.columns;

  return (
    <>
      <div className={CLS.heading}>
        {t.journal.title}
        <span className="flex-1" />
        <span className={CLS.headingMeta}>{t.journal.meta(rows.length)}</span>
      </div>

      {rows.length === 0 ? (
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
              {rows.map((r) => (
                <tr
                  key={r.ts}
                  onClick={() => open(r.ts)}
                  className={cn("cursor-pointer", r.ts === selected ? "bg-panel" : "hover:bg-panel")}
                >
                  <td className={cn(CLS.td, "whitespace-nowrap tabular-nums text-ink/45")}>
                    <span className="text-ink/32">{day(r.ts)}</span> {clock(r.ts)}
                  </td>
                  <td className={CLS.td}>
                    <span className={cn("whitespace-nowrap font-mono text-[10px] font-bold leading-none tracking-[.08em]",
                      r.decision.approved ? "text-pass" : "text-fail")}>
                      {r.decision.approved ? t.journal.approved : t.journal.rejected}
                    </span>
                  </td>
                  <td className={CLS.td}>{r.decision.underlying ? <Ticker symbol={r.decision.underlying} /> : "—"}</td>
                  <td className={cn(CLS.td, "text-ink")}>{r.decision.structure ?? "—"}</td>
                  <td className={cn(CLS.td, "whitespace-nowrap tabular-nums")}>
                    {r.passedCount}/{r.total}
                  </td>
                  <td className={CLS.td}>
                    {r.failed.length ? (
                      <span className="text-fail-ink">{r.failed.map((g) => g.gate).join(", ")}</span>
                    ) : (
                      <span className="text-ink/32">—</span>
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
