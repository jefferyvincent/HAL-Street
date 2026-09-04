import { cn } from "@/lib/cn";
import { Note } from "@/components/Icon";
import { useLegTable, type LegLine } from "@/hooks/useLegTable";
import { useStrings } from "@/hooks/useStrings";
import type { LegMark, StructureChart as Chart } from "@/types";

/**
 * Every leg of a structure, with what it filled at and what it has done since.
 *
 * "The spread is ten dollars down" invites exactly one follow-up question, and until
 * the opening order's per-leg fills were kept there was nothing in this system that
 * could answer it — the ledger recorded the net and discarded the rest.
 *
 * The two sources and their merge are `useLegTable`; nothing is recomputed here.
 */
export function LegTable({ chart, live }: {
  chart: Chart | null;
  live: { legs?: LegMark[] } | null | undefined;
}) {
  const t = useStrings();
  const { lines, nowHeading, pending } = useLegTable(chart, live);

  if (lines.length === 0) return null;

  return (
    <div className="mt-3">
      <div className="flex items-center gap-2 border border-b-0 border-line bg-panel px-3 py-[7px]">
        <span className="font-mono text-[9px] font-bold leading-none tracking-[.12em] text-ink/50">
          {t.chart.legs}
        </span>
        <span className="flex-1" />
        <Head className="w-[74px]">{t.chart.legFill}</Head>
        <Head className="w-[74px]">{nowHeading}</Head>
        <Head className="w-[86px]">{t.chart.legPnl}</Head>
      </div>

      <div className="border border-line bg-panel">
        {lines.map((leg) => <Line key={leg.symbol} leg={leg} />)}
      </div>

      {pending && <Note>{t.chart.legsPending}</Note>}
      <Note>{t.chart.legsNote}</Note>
    </div>
  );
}

function Line({ leg }: { leg: LegLine }) {
  return (
    <div className="flex items-center gap-2 border-b border-line-soft px-3 py-[7px] last:border-b-0">
      {/* Signed contracts after size, so a two-lot reads as the two lots the
          account is actually holding rather than as the one-spread ratio. */}
      <span className={cn("w-[34px] shrink-0 font-mono text-[10px] font-bold leading-none tabular-nums",
        leg.short ? "text-fail" : "text-pass")}
            title={leg.side}>
        {leg.qty}
      </span>
      <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] leading-[1.2] text-ink">
        {leg.symbol}
      </span>
      <Cell className="w-[74px]">
        <span className={leg.hasBasis ? undefined : "text-ink/25"}>{leg.basis}</span>
      </Cell>
      <Cell className="w-[74px]">
        <span className={leg.hasNow ? undefined : "text-ink/25"}>{leg.now}</span>
      </Cell>
      <Cell className={cn("w-[86px] font-semibold",
        leg.pnlSign === null ? "text-ink/25" : leg.pnlSign >= 0 ? "text-pass" : "text-fail")}>
        {leg.pnl}
      </Cell>
    </div>
  );
}

/** A column heading, sized to match the cell beneath it so the two stay aligned. */
function Head({ children, className }: { children: React.ReactNode; className: string }) {
  return (
    <span className={cn("shrink-0 text-right font-mono text-[8.5px] font-bold",
      "leading-none tracking-[.08em] text-ink/35", className)}>
      {children}
    </span>
  );
}

function Cell({ children, className }: { children: React.ReactNode; className: string }) {
  return (
    <span className={cn("shrink-0 text-right font-mono text-[11px] leading-none tabular-nums text-ink/75",
      className)}>
      {children}
    </span>
  );
}
