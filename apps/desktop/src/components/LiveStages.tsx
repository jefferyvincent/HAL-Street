import { cn } from "@/lib/cn";
import { CLS } from "@/constants/theme";
import { useLiveCommittee } from "@/hooks/useLiveCommittee";

/**
 * Which of the four calls the desk is on, compact, for the 200px rail.
 *
 * The tab has the desk itself — five seats and what each one said. This is the
 * same progression at rail width: three words and a dot, enough to see where the
 * committee is without turning the rail into the thing you are reading.
 *
 * Three words and a dot: enough to see which of the four calls the desk is on without
 * turning the rail into the thing you are reading. The tab is where the argument goes.
 */
export function LiveStages() {
  const rows = useLiveCommittee();
  if (!rows) return null;

  return (
    <ul className="mt-[7px] flex flex-col gap-[4px]">
      {rows.map((row) => (
        <li key={row.key}
            className={cn("flex items-center gap-[5px] font-mono text-[9px] leading-none tracking-[.06em]",
              row.state === "running" ? "text-amber"
                : row.state === "done" ? "text-ink/45" : "text-ink/22")}>
          {row.state === "running"
            ? <span className={cn(CLS.dot, "animate-pulse bg-amber")} />
            : <span className={cn(CLS.dot, row.state === "done" ? "bg-ink/40" : "bg-ink/15")} />}
          {row.label}
        </li>
      ))}
    </ul>
  );
}
