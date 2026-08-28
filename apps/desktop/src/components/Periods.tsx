import { cn } from "@/lib/cn";
import { ICON } from "@/constants/icons";
import { STROKE } from "@/constants/theme";
import { Icon, Note } from "@/components/Icon";
import { Trend } from "@/components/Trend";
import { usePeriods, type PeriodFigure } from "@/hooks/usePeriods";
import { useStrings } from "@/hooks/useStrings";

/**
 * P&L over the windows a trader asks for: today, this week, this month, this year.
 *
 * **Two numbers per row, and they are not the same number.** Realized is what closed
 * trades actually made — exact, off the ledger, and zero on a day the desk held rather
 * than a day it lost. Mark-to-market moves with open positions and is what most people
 * mean by "today's P&L". Collapsing them into one figure would make a held position's
 * drift look like a booked loss, or hide a booked loss behind a drifting gain.
 *
 * Calendar windows, not trailing ones. "This month" is since the first, not the last
 * thirty days. Which figure is a dash, and which zero is flat, is decided in
 * `usePeriods`.
 */
export function Periods() {
  const t = useStrings();
  const { rows, shortNote } = usePeriods();
  if (rows.length === 0) return null;

  return (
    <div className="border border-line bg-panel">
      <div className="flex items-center gap-2 border-b border-line px-3 py-[9px]">
        <Icon d={ICON.candles} stroke={STROKE.amber} width={2.2} />
        <span className="font-mono text-[10px] font-bold leading-none tracking-[.12em] text-ink/60">
          {t.periods.title}
        </span>
        <span className="flex-1" />
        <span className="w-[92px] shrink-0 text-right font-mono text-[8.5px] font-bold leading-none tracking-[.08em] text-ink/35">
          {t.periods.realized}
        </span>
        <span className="w-[92px] shrink-0 text-right font-mono text-[8.5px] font-bold leading-none tracking-[.08em] text-ink/35">
          {t.periods.marked}
        </span>
      </div>

      <ul>
        {rows.map((p) => (
          <li key={p.key}
              className="flex items-center gap-2 border-b border-line-soft px-3 py-[8px] last:border-b-0">
            <span className="w-[46px] shrink-0 font-mono text-[10px] font-bold leading-none tracking-[.1em] text-ink/70">
              {p.label}
            </span>
            <span className="min-w-0 flex-1 truncate font-mono text-[9.5px] leading-none text-ink/25">
              {p.closed}
            </span>
            <Figure figure={p.realized} />
            <Figure figure={p.marked} />
          </li>
        ))}
      </ul>

      {shortNote && <Note>{shortNote}</Note>}
      <Note>{t.periods.note}</Note>
    </div>
  );
}

/** One figure, coloured by sign — and drawn flat where the sign means nothing. */
function Figure({ figure }: { figure: PeriodFigure }) {
  if (figure.missing) {
    return (
      <span className="w-[92px] shrink-0 text-right font-mono text-[11px] leading-none text-ink/20">
        {figure.value}
      </span>
    );
  }
  return (
    <span className={cn("flex w-[92px] shrink-0 items-center justify-end gap-[4px]",
      "font-mono text-[11.5px] font-semibold leading-none tabular-nums",
      figure.sign === null ? "text-ink/30" : figure.sign >= 0 ? "text-pass" : "text-fail")}>
      {figure.sign !== null && <Trend value={figure.sign} size={9} />}
      {figure.value}
    </span>
  );
}
