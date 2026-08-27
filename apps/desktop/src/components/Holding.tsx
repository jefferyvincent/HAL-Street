import { cn } from "@/lib/cn";
import { ago, money } from "@/lib/format";
import { ICON } from "@/constants/icons";
import { STROKE } from "@/constants/theme";
import { Icon } from "@/components/Icon";
import { PatternBadge } from "@/components/PatternBadge";
import { Ticker } from "@/components/Ticker";
import { useStrings } from "@/hooks/useStrings";
import { useMarks } from "@/hooks/useMarks";
import { useConnection } from "@/stores/connection";
import { useUI } from "@/stores/ui";

/**
 * What the account is holding, on the view people actually land on.
 *
 * Open positions lived only in the BOOK tab, which is the wrong place for the one
 * thing a person opening a trading console wants first — and on a day when nothing
 * had been gated, the console said "no proposal has been gated yet" while the agent
 * was carrying a live spread.
 *
 * The P&L here is the agent's own last read rather than a live quote, and it is
 * stamped as such. The snapshot is polled every five seconds and must not reach the
 * broker; the agent prices the whole book every cycle anyway, so the freshest
 * honest number is already written down. A number labelled a cycle old is worth
 * more than one that looks live and is not.
 */
export function Holding() {
  const t = useStrings();
  const positions = useConnection((s) => s.snapshot?.positions) ?? [];
  const chart = useUI((s) => s.chart);
  const live = useMarks();

  return (
    <div className="border border-line bg-panel">
      <div className="flex items-center gap-2 border-b border-line px-3 py-[9px]">
        <Icon d={ICON.candles} stroke={STROKE.amber} width={2.2} />
        <span className="font-mono text-[10px] font-bold leading-none tracking-[.12em] text-ink/60">
          {t.console.holding}
        </span>
        <span className="font-mono text-[10px] leading-none text-ink/30 tabular-nums">
          {positions.length}
        </span>
      </div>

      {positions.length === 0 ? (
        <div className="px-3 py-[10px] font-sans text-[11.5px] leading-[1.4] text-ink/35">
          {t.console.holdingNone}
        </div>
      ) : (
        <ul>
          {positions.map((p) => {
            // Live where the broker answered, the agent's own last mark otherwise.
            // Never both, and always labelled with which — a number whose age is
            // unknown is worth less than a stale one that says so.
            const now = live?.marks[p.structure_id];
            const read = p.read;
            const unpriceable = now?.missing?.length ?? 0;
            const value = now?.unrealized_usd ?? read?.unrealized_usd ?? null;
            const fresh = now?.unrealized_usd != null;
            const pnl = value == null ? null : Number(value);
            return (
              <li key={p.structure_id}
                  onClick={() => chart(p.structure_id)}
                  className="cursor-pointer border-b border-line-soft px-3 py-[9px] last:border-b-0 hover:bg-sunk">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  {/* The root, always, from the position's own field rather than
                      from its name. Structures opened before the name carried a
                      ticker still have none, and rewriting the ledger to match code
                      written after the trade would be editing a record. */}
                  <Ticker symbol={p.underlying} />
                  <span className="min-w-0 font-mono text-[12px] font-semibold leading-[1.3] text-ink">
                    {stripRoot(p.name, p.underlying)}
                  </span>
                  <span className="font-mono text-[10px] leading-none text-ink/40 tabular-nums">
                    ×{p.qty}
                  </span>
                  <span className="flex-1" />
                  {pnl === null ? (
                    <span className="font-mono text-[10px] leading-none text-ink/30">
                      {unpriceable ? t.console.partial(unpriceable) : t.console.unpriced}
                    </span>
                  ) : (
                    <span className={cn("font-mono text-[12px] font-bold leading-none tabular-nums",
                      pnl >= 0 ? "text-pass" : "text-fail")}>
                      {money(value!)}
                    </span>
                  )}
                </div>
                <div className="mt-[5px] flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <PatternBadge position={p} />
                  <span className="flex-1" />
                  {read?.dte != null && (
                    <span className="font-mono text-[10px] leading-none text-ink/35 tabular-nums">
                      {t.console.dte(read.dte)}
                    </span>
                  )}
                  {(fresh || read) && (
                    <span className={cn("font-mono text-[10px] leading-none",
                      fresh ? "text-pass/70" : "text-ink/25")}>
                      {fresh
                        ? t.console.asOf(t.console.live)
                        : t.console.asOf(ago(read!.as_of))}
                    </span>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/**
 * The structure's name without a leading ticker, so it is never printed twice.
 *
 * Names built after the root was added begin with it; older ones do not. The panel
 * shows the underlying from its own field either way, and this keeps
 * "QQQ QQQ 2026-10-16 ..." from happening on the new ones.
 */
function stripRoot(name: string, root: string): string {
  return name.startsWith(`${root} `) ? name.slice(root.length + 1) : name;
}
