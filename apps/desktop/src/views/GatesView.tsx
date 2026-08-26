import { FAMILY_ICON } from "@/constants/icons";
import { CLS, STROKE } from "@/constants/theme";
import { Icon, Note } from "@/components/Icon";
import { useGateChain } from "@/hooks/useGateChain";
import { useStrings } from "@/hooks/useStrings";

/**
 * The chain as loaded, in the order it evaluates, with how often each gate has
 * actually rejected something.
 *
 * A gate list nobody can check against the run is decoration. This one is built from
 * the same `ALL_GATES` the agent walks — served, not written here — and counted from
 * the journal, so a gate that has never fired says so.
 */
export function GatesView() {
  const t = useStrings();
  const { groups, total, seen } = useGateChain();

  return (
    <>
      <div className={CLS.heading}>
        {t.gates.title}
        <span className="flex-1" />
        <span className={CLS.headingMeta}>{t.gates.meta(total, seen)}</span>
      </div>

      {groups.map((group) => (
        <div key={group.family}>
          <div className={`${CLS.caption} text-ink/40`}>
            {(t.families[group.family] ?? group.family).toUpperCase()} · {group.gates.length}
          </div>
          <div className="border border-line bg-panel">
            {group.gates.map((g) => (
              <div key={g.gate} className="flex items-center gap-[9px] border-b border-line-soft px-3 py-[8px] last:border-b-0">
                <Icon d={FAMILY_ICON[group.family] ?? FAMILY_ICON.other!}
                      stroke={g.rejected ? STROKE.fail : STROKE.faint} />
                <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] leading-[1.2] text-ink">
                  {g.gate}
                </span>
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

      <Note>{t.gates.note(seen)}</Note>
    </>
  );
}
