import { cn } from "@/lib/cn";
import { short } from "@/lib/format";
import { ICON } from "@/constants/icons";
import { CLS, STROKE } from "@/constants/theme";
import { useStrings } from "@/hooks/useStrings";
import type { FamilyGroup } from "@/hooks/useGateFamilies";
import { Cross, Icon, Tick } from "./Icon";

/**
 * Every verdict from one decision, grouped by family.
 *
 * All of them, not just the failures. A chain that shows only what it caught says
 * nothing about what it looked at, and "15 ran, 5 rejected" is the claim this project
 * is actually making.
 */
export function GateLedger({ families, total, failed }: {
  families: FamilyGroup[];
  total: number;
  failed: number;
}) {
  const t = useStrings();

  return (
    <div className="min-w-0 p-3">
      <div className="mb-[9px] flex items-center gap-[7px]">
        <Icon d={ICON.chain} size={14} stroke={STROKE.amber} />
        <span className="font-mono text-[10px] font-bold leading-none tracking-[.12em] text-ink">
          {t.ledger.allRan(total)}
        </span>
        <span className="flex-1" />
        <span className="font-mono text-[10px] font-semibold leading-none tabular-nums text-pass">{total - failed}</span>
        <span className="font-mono text-[10px] font-semibold leading-none tabular-nums text-fail">{failed}</span>
      </div>

      {families.map((f) => (
        <div key={f.family}>
          <div className={cn(CLS.caption, f.failed ? "text-fail" : "text-ink/40")}>
            {(t.families[f.family] ?? f.family).toUpperCase()}
          </div>
          {f.gates.map((g) => (
            <div
              key={g.gate}
              className={cn("flex items-center gap-2 border-b border-line-soft py-[5px]",
                !g.passed && "-mx-2 bg-fail/15 px-2")}
            >
              {g.passed ? <Tick /> : <Cross />}
              <span
                className={cn("min-w-0 flex-1 truncate font-mono text-[11px] leading-[1.2]",
                  g.passed ? "font-normal text-ink" : "font-semibold text-fail-ink")}
                title={g.gate}
              >
                {g.gate}
              </span>
              <span
                className={cn("whitespace-nowrap font-mono text-[9.5px] leading-none",
                  g.passed ? "font-normal text-ink/40" : "font-semibold text-fail")}
                title={g.reason}
              >
                {short(g.reason)}
              </span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
