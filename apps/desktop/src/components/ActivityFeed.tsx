import { cn } from "@/lib/cn";
import { ICON } from "@/constants/icons";
import { STROKE } from "@/constants/theme";
import { Icon } from "@/components/Icon";
import { useFormat } from "@/hooks/useFormat";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

/**
 * The run as a pulse: scanning, reading the tape, deliberating, declining.
 *
 * This exists because the panel was built entirely around gate decisions, and an
 * agent that declines every cycle produces none — so on a day of considered passes
 * every view was empty and the whole thing read as broken. Most of what this agent
 * does is not a decision, and none of it was visible anywhere.
 *
 * Newest last, like a terminal, because it is read as a trailing log rather than
 * scanned as a table.
 */
export function ActivityFeed() {
  const t = useStrings();
  const f = useFormat();
  const rows = useConnection((s) => s.snapshot?.activity) ?? [];
  if (rows.length === 0) return null;

  return (
    <div className="border border-line bg-panel">
      <div className="flex items-center gap-2 border-b border-line px-3 py-[9px]">
        <Icon d={ICON.pulse} stroke={STROKE.amber} width={2.2} />
        <span className="font-mono text-[10px] font-bold leading-none tracking-[.12em] text-ink/60">
          {t.console.activity}
        </span>
      </div>
      <ul className="max-h-[340px] overflow-y-auto">
        {rows.map((r, i) => (
          <li key={`${r.ts}-${i}`}
              className="flex items-baseline gap-2 border-b border-line-soft px-3 py-[5px] last:border-b-0">
            <span className="shrink-0 font-mono text-[10px] leading-[1.4] text-ink/25 tabular-nums">
              {f.stamp(r.ts)}
            </span>
            <span className="w-[34px] shrink-0 font-mono text-[10px] font-semibold leading-[1.4] text-ink/45">
              {r.underlying}
            </span>
            <span className={cn("min-w-0 font-sans text-[11.5px] leading-[1.4]",
              r.event === "error" || r.event === "halt" ? "text-fail"
                : r.event === "gate_decision" || r.event === "order" ? "text-ink/75"
                : "text-ink/50")}>
              {r.detail}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
