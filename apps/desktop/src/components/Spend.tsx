import { cn } from "@/lib/cn";
import { ICON } from "@/constants/icons";
import { STROKE } from "@/constants/theme";
import { Icon, Note } from "@/components/Icon";
import { useSpend } from "@/hooks/useSpend";
import { useStrings } from "@/hooks/useStrings";

/**
 * What the thinking has cost: tokens always, money where a price is known.
 *
 * The committee is four model calls where the single-call path is one, and that is a
 * defensible trade only if somebody can see the bill. It was invisible — the figures
 * were in the journal and on no screen.
 *
 * Split by model, because the three research stages run a tier below the judge and a
 * single total stopped having a price the moment they did. Five thousand tokens is
 * not a number until you know what spent them.
 *
 * The floor, the split and the qualifier are all decided in `useSpend`. See
 * `telemetry/pricing.py`: prices are configuration, and the one shipped is the one
 * that could be sourced.
 */
export function Spend() {
  const t = useStrings();
  const spend = useSpend();
  if (!spend) return null;

  return (
    <div className="border border-line bg-panel">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-[9px]">
        <Icon d={ICON.committee} stroke={STROKE.amber} width={2.2} />
        <span className="font-mono text-[10px] font-bold leading-none tracking-[.12em] text-ink/60">
          {t.spend.title}
        </span>
        <span className="font-mono text-[10px] leading-none text-ink/30 tabular-nums">
          {spend.cycles}
        </span>
        <span className="flex-1" />
        {/* The headline number, and the qualifier attached to it rather than
            printed underneath where it can be read separately. */}
        <span className="font-mono text-[13px] font-bold leading-none tabular-nums text-ink">
          {spend.total}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-px bg-line">
        {spend.figures.map((figure) => (
          <Figure key={figure.key} label={figure.label} value={figure.value}
                  note={figure.note} />
        ))}
      </div>

      <ul className="border-t border-line">
        {spend.models.map((m) => <Row key={m.model} model={m} />)}
        {spend.stray && <Row model={spend.stray} muted />}
      </ul>

      {spend.unpriced && <Note>{t.spend.noPriceNote(spend.unpriced)}</Note>}
      {spend.stray && <Note>{t.spend.unattributedNote}</Note>}
    </div>
  );
}

/** One model's line: what it spent, and what that cost where a price is known. */
function Row({ model, muted = false }: {
  model: { model: string; split: string; cost: string; priced: boolean };
  muted?: boolean;
}) {
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line-soft px-3 py-[7px] last:border-b-0">
      <span className={cn("font-mono text-[11px] leading-none",
        muted ? "text-ink/45" : "text-ink")}>
        {model.model}
      </span>
      <span className="font-mono text-[10px] leading-none tabular-nums text-ink/40">
        {model.split}
      </span>
      <span className="flex-1" />
      <span className={cn("font-mono text-[11px] leading-none tabular-nums",
        model.priced ? "font-semibold text-ink/75" : "text-ink/30")}>
        {model.cost}
      </span>
    </li>
  );
}

function Figure({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="bg-panel px-3 py-[9px]" title={note}>
      <div className="font-mono text-[8.5px] font-bold leading-none tracking-[.08em] text-ink/40">
        {label}
      </div>
      <div className="mt-[5px] font-mono text-[13px] font-semibold leading-none tabular-nums text-ink">
        {value}
      </div>
    </div>
  );
}
