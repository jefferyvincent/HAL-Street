import { cn } from "@/lib/cn";
import { useFormat } from "@/hooks/useFormat";
import { FAMILY_ICON } from "@/constants/icons";
import { CLS, STROKE } from "@/constants/theme";
import { Icon, Note } from "@/components/Icon";
import { useGateChain } from "@/hooks/useGateChain";
import { useLimits } from "@/hooks/useLimits";
import { useStrings } from "@/hooks/useStrings";

/**
 * The chain as loaded, in the order it evaluates, with what each gate measured the
 * last time it ran and how often it has rejected something.
 *
 * A gate list nobody can check against the run is decoration — sixteen names and a
 * count answer "does this gate exist" and "has it ever bitten", neither of which is a
 * question anyone has while watching a book. The reading is: `2/20 open positions`,
 * `1/6 entries this hour`, `within the 5% floor of $89,817`. Those are the numbers
 * that decide whether the next proposal gets through.
 *
 * Nothing here is interactive, and that is the design rather than an omission. The
 * limits live in `.env`, so changing one is a diff someone can review; a field in a
 * dashboard that moves a risk limit leaves no such trace, and the socket this panel
 * listens on is never read from at all. This tab is the instrument panel for the
 * deterministic half — it is the half that says no, and being unable to argue with it
 * from here is the point.
 */
export function GatesView() {
  const f = useFormat();
  const t = useStrings();
  const { groups, total, seen, readAt, readOf, afterHoursNote } = useGateChain();
  const limits = useLimits();

  return (
    <>
      <div className={CLS.heading}>
        {t.gates.title}
        <span className="flex-1" />
        <span className={CLS.headingMeta}>{t.gates.meta(total, seen)}</span>
      </div>

      {readAt && (
        <div className={`${CLS.caption} text-ink/35`}>
          {t.gates.readAt(readOf, f.ago(readAt))}
        </div>
      )}

      {afterHoursNote && <Note>{afterHoursNote}</Note>}

      {groups.map((group) => (
        <div key={group.family}>
          <div className={`${CLS.caption} text-ink/40`}>
            {t.gates.familyHeading((t.families[group.family] ?? group.family).toUpperCase(), group.gates.length)}
          </div>
          <div className="border border-line bg-panel">
            {group.gates.map((g) => (
              <div key={g.gate}
                   className="flex flex-wrap items-baseline gap-x-[9px] gap-y-1 border-b border-line-soft px-3 py-[8px] last:border-b-0">
                <Icon d={FAMILY_ICON[group.family] ?? FAMILY_ICON.other!}
                      stroke={g.rejected ? STROKE.fail : STROKE.faint} />
                <span className="font-mono text-[11.5px] leading-[1.2] text-ink">
                  {g.gate}
                </span>
                {/* The gate's own words. Never recomputed here: a panel that
                    re-derives a limit check is one that can disagree with the thing
                    it depicts, and this is the half of the system that says no. */}
                {g.reading && (
                  <span className={cn("min-w-0 flex-1 truncate font-mono text-[10.5px] leading-[1.3] tabular-nums",
                    g.passed ? "text-ink/45" : "text-fail")}
                        title={g.reading}>
                    {g.reading}
                  </span>
                )}
                <span className="flex-1" />
                {g.rejected ? (
                  <span className="whitespace-nowrap font-mono text-[10px] font-semibold leading-none tabular-nums text-fail">
                    {t.gates.rejectedCount(g.rejected)}
                  </span>
                ) : (
                  <span className="whitespace-nowrap font-mono text-[10px] leading-none text-ink/32">
                    {t.gates.neverRejected}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* The numbers the readings above are measured against. A gate reporting
          "2/20 open positions" means little without the 20 beside it, and these had
          been in the left rail that became the committee. */}
      <div className={`${CLS.caption} text-ink/40`}>{t.gates.limits}</div>
      <div className="border border-line bg-panel">
        {limits.map((l) => (
          // `min-w-0` on the name and `shrink-0` on the value. A flex child will not
          // shrink below its content by default, so a name like
          // MAX_LOSS_PER_POSITION_USD pushed the number straight out of the card —
          // and the number is the half that matters. The name wraps instead.
          <div key={l.name}
               className="flex items-baseline justify-between gap-3 border-b border-line-soft px-3 py-[7px] last:border-b-0">
            <span className="min-w-0 break-all font-mono text-[10px] leading-[1.3] text-ink/45">
              {l.name}
            </span>
            <span className="shrink-0 whitespace-nowrap font-mono text-[11px] font-semibold leading-[1.3] tabular-nums text-ink">
              {l.value}
            </span>
          </div>
        ))}
      </div>

      <Note>{t.gates.limitsNote}</Note>
      <Note>{t.gates.note(seen)}</Note>
      <Note>{t.gates.readOnly}</Note>
    </>
  );
}
