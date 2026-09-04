import { useFormat } from "@/hooks/useFormat";
import { cn } from "@/lib/cn";
import { CLS } from "@/constants/theme";
import { useEquityChart } from "@/hooks/useEquityChart";
import { useStrings } from "@/hooks/useStrings";
import type { EquityPoint, Pnl } from "@/types";

/**
 * Account equity at the start of every scan cycle.
 *
 * All of the charting lives in `useEquityChart`; this renders a frame, a ref, and the
 * two figures beside it. Two things the chart deliberately does not do: it draws no
 * projection or fit — every point is a reading — and it never resamples, because
 * duplicate consecutive values are real and flattening them would hide exactly the
 * quiet stretches that say the agent was running and finding nothing worth taking.
 */
export function EquityChart({ curve, pnl }: { curve: EquityPoint[]; pnl: Pnl }) {
  const f = useFormat();
  const t = useStrings();
  const { host, drawable, count, move } = useEquityChart(curve, pnl);

  return (
    <div className="border border-line bg-panel">
      <div className="flex items-baseline gap-[9px] border-b border-line px-3 py-[7px]">
        <span className="font-mono text-[10px] font-bold leading-none tracking-[.12em] text-ink/60">
          {t.equity.title}
        </span>
        <span className="flex-1" />
        {move !== null && (
          <span className={cn("font-mono text-[10px] font-semibold leading-none tabular-nums",
            move < 0 ? "text-fail" : "text-pass")}>
            {f.signed(move)}
          </span>
        )}
        <span className="font-mono text-[10px] leading-none tabular-nums text-ink/40">
          {f.money(pnl.equity_last)}
        </span>
      </div>

      {drawable ? (
        <div ref={host} className="h-[150px] w-full" />
      ) : (
        <div className={CLS.empty}>{count === 0 ? t.equity.none : t.equity.one}</div>
      )}

      <div className="flex items-center gap-3 border-t border-line-soft px-3 py-[6px] font-mono text-[9.5px] leading-none tabular-nums text-ink/40">
        <span>{t.equity.scans(count)}</span>
        <span>{t.equity.drawdown(f.money(pnl.max_drawdown_usd), f.plain(pnl.max_drawdown_pct))}</span>
      </div>
    </div>
  );
}
