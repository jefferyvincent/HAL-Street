import { cn } from "@/lib/cn";
import { ICON } from "@/constants/icons";
import { STROKE } from "@/constants/theme";
import { Icon } from "@/components/Icon";
import { useScoreboard } from "@/hooks/useScoreboard";
import { Trend } from "@/components/Trend";
import { useStrings } from "@/hooks/useStrings";

/**
 * How the run is going, on the view people land on.
 *
 * The equity curve sat in the right-hand rail, which stacks below the fold under
 * 1181px — so on an ordinary window the one thing anyone opens a trading console
 * for was off-screen. These are the same figures `./start.sh report` prints, from
 * the same journal and ledger, so the screen and the write-up cannot disagree.
 *
 * Colour only where a sign means something. A win/loss record is not better for
 * being green, and a drawdown is not a failure — colouring either would be
 * decoration pretending to be information.
 */
export function Scoreboard() {
  const t = useStrings();
  const stats = useScoreboard();
  if (stats.length === 0) return null;

  return (
    <div className="border border-line bg-panel">
      <div className="flex items-center gap-2 border-b border-line px-3 py-[9px]">
        <Icon d={ICON.pulse} stroke={STROKE.amber} width={2.2} />
        <span className="font-mono text-[10px] font-bold leading-none tracking-[.12em] text-ink/60">
          {t.scoreboard.title}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-px bg-line-soft sm:grid-cols-4">
        {stats.map((s) => (
          <div key={s.key} className="min-w-0 bg-panel px-3 py-[10px]">
            <div className="font-mono text-[9px] font-bold leading-none tracking-[.12em] text-ink/32">
              {s.label}
            </div>
            <div className={cn("mt-[6px] flex items-center gap-[5px] break-words font-mono text-[14px] font-bold leading-[1.15] tabular-nums",
              s.sign === "up" ? "text-pass" : s.sign === "down" ? "text-fail" : "text-ink")}>
              {s.sign && <Trend value={s.sign === "up" ? 1 : -1} size={10} />}
              {s.value}
            </div>
            {s.note && (
              <div className="mt-[4px] font-sans text-[10px] leading-[1.35] text-ink/35">
                {s.note}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
