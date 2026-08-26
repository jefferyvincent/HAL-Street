import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

/**
 * The latch, when it is closed.
 *
 * It says how to clear it and does not offer to: clearing a halt is a deliberate act
 * at the CLI, where it lands in shell history. A button here would make it something
 * a person can do twice by accident while watching a position move against them —
 * which is the exact moment the latch exists for.
 */
export function HaltBanner() {
  const t = useStrings();
  const circuit = useConnection((s) => s.snapshot?.circuit);
  if (!circuit?.halted) return null;

  return (
    <div className="flex items-baseline gap-[10px] border-b border-fail/45 bg-fail/14 px-[14px] py-[9px] font-sans text-[12.5px] leading-[1.5] text-fail-ink">
      <b className="font-mono text-[10px] font-bold leading-none tracking-[.1em] text-fail">{t.halt.tag}</b>
      <span>{t.halt.detail(circuit.halt_reason)}</span>
    </div>
  );
}
