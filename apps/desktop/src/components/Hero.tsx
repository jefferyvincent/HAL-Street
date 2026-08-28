import { cn } from "@/lib/cn";
import { CLS } from "@/constants/theme";
import { useHero } from "@/hooks/useHero";

/**
 * What the account is worth, and when the agent acts next.
 *
 * The second half is what this exists for. Every other reading on the console answers
 * "what has happened"; none answered "when does something happen next", so a quiet
 * panel between scans could not be told apart from a stopped one — which is most of
 * what has ever been reported about this screen.
 *
 * The figure is large because it is the one number the whole project is about, and it
 * was previously a chrome-bar item smaller than the tab labels beside it.
 */
export function Hero() {
  const hero = useHero();

  return (
    <div className="flex flex-wrap items-end gap-x-8 gap-y-4 border border-line bg-panel px-4 py-[14px]">
      <div className="min-w-0">
        <div className="font-mono text-[9px] font-bold leading-none tracking-[.16em] text-ink/35">
          {hero.equityLabel}
        </div>
        {hero.equity ? (
          <div className="mt-[7px] font-mono text-[34px] font-bold leading-none tracking-[-.01em] text-ink tabular-nums">
            {hero.equity}
          </div>
        ) : (
          // Not a zero. Nothing has priced the account, and a large $0.00 is the most
          // alarming way there is to say "no reading yet".
          <div className="mt-[10px] font-sans text-[12px] leading-none text-ink/30">
            {hero.unknown}
          </div>
        )}
        <div className="mt-[9px] font-mono text-[9.5px] leading-none tabular-nums text-ink/30">
          {hero.stats}
        </div>
      </div>

      {hero.today && (
        <div>
          <div className="font-mono text-[9px] font-bold leading-none tracking-[.16em] text-ink/35">
            {hero.todayLabel}
          </div>
          <div className={cn("mt-[7px] font-mono text-[20px] font-bold leading-none tabular-nums",
            hero.today.up ? "text-pass" : "text-fail")}>
            {hero.today.value}
          </div>
        </div>
      )}

      <span className="flex-1" />

      {hero.timer ? (
        <div className="text-right">
          <div className="font-mono text-[9px] font-bold leading-none tracking-[.16em] text-amber/70">
            {hero.timer.label}
          </div>
          <div className="mt-[7px] font-mono text-[30px] font-bold leading-none text-amber tabular-nums">
            {hero.timer.clock}
          </div>
          <div className="mt-[7px] flex justify-end gap-[14px] font-mono text-[8px] font-bold leading-none tracking-[.14em] text-ink/25">
            {hero.timer.units.map((unit) => <span key={unit}>{unit}</span>)}
          </div>
        </div>
      ) : hero.waiting && (
        <div className="max-w-[280px] text-right">
          <div className="flex items-center justify-end gap-[7px] font-mono text-[9px] font-bold leading-none tracking-[.16em] text-ink/30">
            <span className={cn(CLS.dot, "bg-ink/20")} />
            {hero.waiting.label}
          </div>
          <div className="mt-[6px] font-sans text-[10.5px] leading-[1.45] text-ink/25">
            {hero.waiting.note}
          </div>
        </div>
      )}
    </div>
  );
}
