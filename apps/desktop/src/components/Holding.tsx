import { cn } from "@/lib/cn";
import { clock, money } from "@/lib/format";
import { ICON } from "@/constants/icons";
import { STROKE } from "@/constants/theme";
import { Icon } from "@/components/Icon";
import { PatternBadge } from "@/components/PatternBadge";
import { useStrings } from "@/hooks/useStrings";
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
            const read = p.read;
            const pnl = read?.unrealized_usd == null ? null : Number(read.unrealized_usd);
            return (
              <li key={p.structure_id}
                  onClick={() => chart(p.structure_id)}
                  className="cursor-pointer border-b border-line-soft px-3 py-[9px] last:border-b-0 hover:bg-sunk">
                <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                  <span className="font-mono text-[12px] font-semibold leading-[1.3] text-ink">
                    {p.name}
                  </span>
                  <span className="font-mono text-[10px] leading-none text-ink/40 tabular-nums">
                    ×{p.qty}
                  </span>
                  <span className="flex-1" />
                  {pnl === null ? (
                    <span className="font-mono text-[10px] leading-none text-ink/30">
                      {t.console.unpriced}
                    </span>
                  ) : (
                    <span className={cn("font-mono text-[12px] font-bold leading-none tabular-nums",
                      pnl >= 0 ? "text-pass" : "text-fail")}>
                      {money(read!.unrealized_usd!)}
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
                  {read && (
                    <span className="font-mono text-[10px] leading-none text-ink/25">
                      {t.console.asOf(clock(read.as_of))}
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
