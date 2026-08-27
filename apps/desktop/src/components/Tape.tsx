import { cn } from "@/lib/cn";
import { clock } from "@/lib/format";
import { ICON } from "@/constants/icons";
import { CLS, STROKE } from "@/constants/theme";
import type { Row } from "@/lib/decisions";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";
import { useUI } from "@/stores/ui";
import { Cross, Icon, Tick } from "./Icon";
import { Ticker } from "./Ticker";

/** The run as it happened, newest first, with the equity curve above it. */
export function Tape({ rows, selected }: { rows: Row[]; selected: string | null }) {
  const t = useStrings();
  const show = useUI((s) => s.showDecision);
  const chart = useUI((s) => s.chart);
  const snap = useConnection((s) => s.snapshot);
  if (!snap) return null;

  return (
    <aside className="min-w-0 border-t border-line bg-sunk min-[1181px]:border-t-0 min-[1181px]:border-l">
      <div className="flex items-center gap-2 border-y border-line px-3 py-[9px]">
        <Icon d={ICON.pulse} stroke={STROKE.amber} width={2.2} />
        <span className="font-mono text-[10px] font-bold leading-none tracking-[.12em] text-ink/60">
          {t.tape.title}
        </span>
      </div>
      <div className="flex items-center gap-2 border-b border-line-soft px-3 py-[7px]">
        <span className="font-mono text-[10px] leading-[1.4] tabular-nums text-ink/40">
          {t.tape.counts(snap.pnl.approved, snap.pnl.rejected, snap.pnl.passed)}
        </span>
      </div>

      {rows.length === 0 ? (
        <div className={CLS.empty}>{t.tape.empty}</div>
      ) : (
        rows.map((r) => (
          <button
            key={r.ts}
            onClick={() => show(r.ts)}
            className={cn(
              "block w-full cursor-pointer border-b border-line-soft px-3 py-[10px] text-left hover:bg-panel",
              r.decision.approved ? "shadow-[inset_2px_0_0_#21d07a]" : "shadow-[inset_2px_0_0_#ff4d4f]",
              r.ts === selected && "bg-panel")}
          >
            <div className="flex items-center gap-[6px]">
              {r.decision.approved ? <Tick /> : <Cross />}
              <span className={cn("font-mono text-[9.5px] font-bold leading-none tracking-[.08em]",
                r.decision.approved ? "text-pass" : "text-fail")}>
                {r.decision.approved ? t.tape.approved(r.total) : t.tape.rejected(r.failed.length, r.total)}
              </span>
              {/* A rehearsal gates and journals exactly as a live cycle does and
                  stops before submission, so its records are indistinguishable from
                  a live run's — and a REJECTED written by one was read as the broker
                  refusing an order. Said on the row, not only in the chrome. */}
              {r.decision.dry_run && (
                <span className="border border-line px-[5px] py-[2px] font-mono text-[8.5px] font-bold leading-none tracking-[.1em] text-ink/40"
                      title={t.tape.dryRunTitle}>
                  {t.tape.dryRun}
                </span>
              )}
              <span className="flex-1" />
              <span className="font-mono text-[10px] leading-none tabular-nums text-ink/35">{clock(r.ts)}</span>
            </div>
            <div className="mt-[6px] truncate font-mono text-[11px] font-semibold leading-[1.4] text-ink">
              {r.decision.structure}
            </div>
            <div className="mt-[3px] flex items-center gap-2 font-sans text-[10.5px] leading-[1.45] text-ink/60">
              <span className="min-w-0 flex-1 truncate">
                {r.failed.length ? r.failed.map((g) => g.gate).join("; ") : ""}
              </span>
              {r.decision.underlying && <Ticker symbol={r.decision.underlying} />}
              {/* Straight to the position, where the decision became one. Nested
                  inside a button, so it is a span with a role rather than a second
                  <button> — which is invalid markup and swallows its own click. */}
              {r.decision.structure_id && (
                <span
                  role="link"
                  tabIndex={0}
                  onClick={(e) => { e.stopPropagation(); chart(r.decision.structure_id!); }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      e.stopPropagation();
                      chart(r.decision.structure_id!);
                    }
                  }}
                  className="shrink-0 cursor-pointer font-mono text-[9px] font-bold leading-none
                             tracking-[.08em] text-amber hover:opacity-70
                             focus-visible:outline focus-visible:outline-1 focus-visible:outline-amber">
                  {t.tape.viewTrade}
                </span>
              )}
            </div>
          </button>
        ))
      )}
    </aside>
  );
}
