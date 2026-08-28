import { cn } from "@/lib/cn";
import { ICON } from "@/constants/icons";
import { STROKE } from "@/constants/theme";
import { Icon, Note } from "@/components/Icon";
import { Trend } from "@/components/Trend";
import { usePeriods } from "@/hooks/usePeriods";
import { useStrings } from "@/hooks/useStrings";
import type { PeriodFigure, PeriodRow } from "@/hooks/usePeriods";

/**
 * P&L over the window a trader picks: today, this week, this month, this year.
 *
 * A row of switches and one window's figures, rather than five rows of two. Five rows
 * is a table to read; a desk wants a number to glance at and a way to change which
 * number it is.
 *
 * Two figures, because they are not the same figure. Realized is what closed trades
 * made — exact, and zero on a day the desk held rather than a day it lost, which is
 * why its zero is drawn flat rather than green. Mark-to-market moves with open
 * positions and is what most people mean by "today's P&L".
 */
export function Periods() {
  const t = useStrings();
  const { rows, choose, showing, shortNote } = usePeriods();
  if (!showing) return null;

  return (
    <div className="border border-line bg-panel">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-line px-3 py-[9px]">
        <Icon d={ICON.candles} stroke={STROKE.amber} width={2.2} />
        <span className="font-mono text-[10px] font-bold leading-none tracking-[.12em] text-ink/60">
          {t.periods.title}
        </span>
        <span className="flex-1" />
        {rows.map((r) => (
          <button
            key={r.key}
            onClick={() => choose(r.key)}
            aria-pressed={r.active}
            className={cn("font-mono text-[9.5px] font-bold leading-none tracking-[.08em]",
              "transition-colors hover:text-ink focus-visible:outline",
              "focus-visible:outline-1 focus-visible:outline-amber",
              r.active ? "text-amber" : "text-ink/35")}
          >
            {r.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-px bg-line">
        <Figure label={t.periods.realized} figure={showing.realized} note={showing.closed} />
        <Figure label={t.periods.marked} figure={showing.marked} note={null} />
      </div>

      {shortNote && <Note>{shortNote}</Note>}
      <Note>{t.periods.note}</Note>
    </div>
  );
}

function Figure({ label, figure, note }: {
  label: string; figure: PeriodFigure; note: PeriodRow["closed"] | null;
}) {
  return (
    <div className="bg-panel px-3 py-[10px]">
      <div className="font-mono text-[8.5px] font-bold leading-none tracking-[.08em] text-ink/40">
        {label}
      </div>
      <div className={cn("mt-[6px] flex items-center gap-[5px] font-mono text-[15px] font-bold leading-none tabular-nums",
        figure.missing ? "text-ink/20"
        : figure.sign === null ? "text-ink/40"
        : figure.sign >= 0 ? "text-pass" : "text-fail")}>
        {figure.sign !== null && <Trend value={figure.sign} size={11} />}
        {figure.value}
      </div>
      {note && (
        <div className="mt-[5px] font-mono text-[9.5px] leading-none text-ink/25">{note}</div>
      )}
    </div>
  );
}
