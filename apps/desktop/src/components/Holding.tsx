import { cn } from "@/lib/cn";
import { ICON } from "@/constants/icons";
import { STROKE } from "@/constants/theme";
import { Icon } from "@/components/Icon";
import { PatternBadge } from "@/components/PatternBadge";
import { Sparkline } from "@/components/Sparkline";
import { StructureName } from "@/components/StructureName";
import { Ticker } from "@/components/Ticker";
import { Trend } from "@/components/Trend";
import { useHolding } from "@/hooks/useHolding";
import { useStrings } from "@/hooks/useStrings";

/**
 * What the account is holding, on the view people actually land on.
 *
 * Open positions lived only in the BOOK tab, which is the wrong place for the one
 * thing a person opening a trading console wants first — and on a day when nothing
 * had been gated, the console said "no proposal has been gated yet" while the agent
 * was carrying a live spread.
 *
 * The P&L here is the agent's own last read rather than a live quote, and it is
 * stamped as such. Which figure that is, and how it is labelled, is decided in
 * `useHolding` — this file only draws it.
 */
export function Holding() {
  const t = useStrings();
  const { rows, count, open } = useHolding();

  return (
    <div className="border border-line bg-panel">
      <div className="flex items-center gap-2 border-b border-line px-3 py-[9px]">
        <Icon d={ICON.candles} stroke={STROKE.amber} width={2.2} />
        <span className="font-mono text-[10px] font-bold leading-none tracking-[.12em] text-ink/60">
          {t.console.holding}
        </span>
        <span className="font-mono text-[10px] leading-none text-ink/30 tabular-nums">
          {count}
        </span>
      </div>

      {count === 0 ? (
        <div className="px-3 py-[10px] font-sans text-[11.5px] leading-[1.4] text-ink/35">
          {t.console.holdingNone}
        </div>
      ) : (
        <ul>
          {rows.map((r) => (
            <li key={r.id}
                onClick={() => open(r.id)}
                className="cursor-pointer border-b border-line-soft px-3 py-[9px] last:border-b-0 hover:bg-sunk">
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                {/* Every row here is a position the agent is still carrying — the
                    snapshot builds this list from the ledger's open structures — so
                    the badge is a constant, not a verdict, and needs nothing from the
                    hook. `self-center` because the row aligns on the baseline and a
                    bordered chip has none worth aligning to. */}
                <span className="self-center border border-pass/50 px-[5px] py-[2px] font-mono text-[8.5px] font-bold leading-none tracking-[.1em] text-pass"
                      title={t.console.openTitle}>
                  {t.console.open}
                </span>
                {/* The root, always, from the position's own field rather than
                    from its name. Structures opened before the name carried a
                    ticker still have none, and rewriting the ledger to match code
                    written after the trade would be editing a record. */}
                <Ticker symbol={r.symbol} />
                <StructureName name={r.name}
                               className="font-mono text-[12px] font-semibold leading-[1.3] text-ink" />
                <span className="font-mono text-[10px] leading-none text-ink/40 tabular-nums">
                  {t.console.qty(r.qty)}
                </span>
                <span className="flex-1" />
                {r.pnl === null ? (
                  <span className="font-mono text-[10px] leading-none text-ink/30">
                    {r.value}
                  </span>
                ) : (
                  <span className={cn("flex items-center gap-[5px] font-mono text-[12px] font-bold leading-none tabular-nums",
                    r.pnl >= 0 ? "text-pass" : "text-fail")}>
                    <Trend value={r.pnl} />
                    {r.value}
                  </span>
                )}
              </div>
              <div className="mt-[5px] flex flex-wrap items-center gap-x-3 gap-y-1">
                {/* The shape, not just the number. A position at -$19 could have
                    drifted there all day or fallen off a cliff last cycle, and the
                    card said the same thing either way. Plots P&L rather than the
                    mark — see `Sparkline` for why that distinction is load-bearing
                    on a credit structure. */}
                <Sparkline points={r.spark} />
                <PatternBadge position={r.position} />
                <span className="flex-1" />
                {r.dte && (
                  <span className="font-mono text-[10px] leading-none text-ink/35 tabular-nums">
                    {r.dte}
                  </span>
                )}
                {r.asOf && (
                  <span className={cn("font-mono text-[10px] leading-none",
                    r.fresh ? "text-pass/70" : "text-ink/25")}>
                    {r.asOf}
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
