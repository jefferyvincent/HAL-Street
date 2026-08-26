import { cn } from "@/lib/cn";
import { FAMILY_ICON, ICON } from "@/constants/icons";
import { STROKE } from "@/constants/theme";
import type { FamilyGroup } from "@/hooks/useGateFamilies";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";
import { Icon } from "./Icon";

/**
 * The family meter and the limits, both describing the selected decision.
 *
 * The limits are shown under the environment variable names that set them, with no
 * control beside them. That is the point: a limit changes by editing `.env` and
 * restarting, where the change is a diff someone can see — not by a field in a
 * dashboard that nothing records.
 */
export function Rail({ families }: { families: FamilyGroup[] }) {
  const t = useStrings();
  const limits = useConnection((s) => s.snapshot?.limits) ?? {};

  return (
    <nav className="border-t border-line bg-sunk py-[10px] min-[1181px]:border-t-0 min-[1181px]:border-r">
      <div className="px-3 pb-2 font-mono text-[9px] font-bold leading-none tracking-[.14em] text-ink/32">
        {t.rail.families}
      </div>

      {families.map((f) => (
        <div
          key={f.family}
          className={cn("flex items-center gap-[9px] px-3 py-[7px] font-sans text-[11.5px] leading-none",
            f.failed
              ? "bg-fail/14 font-semibold text-fail-ink shadow-[inset_2px_0_0_#ff4d4f]"
              : "font-normal text-ink/60")}
        >
          <Icon d={FAMILY_ICON[f.family] ?? FAMILY_ICON.other!} size={14}
                stroke={f.failed ? STROKE.fail : STROKE.pass} />
          <span className="flex-1">{t.families[f.family] ?? f.family}</span>
          <span className={cn("font-mono text-[10px] leading-none tabular-nums",
            f.failed ? "font-semibold text-fail" : "font-medium text-ink/40")}>
            {f.failed || f.gates.length}
          </span>
        </div>
      ))}

      <div className="px-3 pt-4 pb-2 font-mono text-[9px] font-bold leading-none tracking-[.14em] text-ink/32">
        {t.rail.limits}
      </div>
      <div className="mx-[10px] border border-line bg-panel">
        {Object.entries(limits).map(([name, value]) => (
          <div key={name} className="flex justify-between gap-2 border-b border-line-soft px-[9px] py-[6px] last:border-b-0">
            <span className="font-mono text-[9.5px] leading-[1.3] text-ink/45">{name}</span>
            <span className="font-mono text-[10px] font-semibold leading-[1.3] tabular-nums text-ink">{value}</span>
          </div>
        ))}
      </div>

      <div className="mx-[10px] mt-[9px] flex gap-[7px] border border-line bg-panel px-[9px] py-2 font-sans text-[10.5px] leading-[1.45] text-ink/40">
        <Icon d={ICON.shield} size={12} stroke={STROKE.muted} width={2.2} />
        <span>{t.rail.limitsNote}</span>
      </div>
    </nav>
  );
}
