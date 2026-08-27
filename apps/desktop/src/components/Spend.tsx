import { cn } from "@/lib/cn";
import { ICON } from "@/constants/icons";
import { STROKE } from "@/constants/theme";
import { Icon, Note } from "@/components/Icon";
import { money, plain } from "@/lib/format";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

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
 * **The dollar figure is a floor, and says so when it is one.** A model with no
 * configured price contributes its tokens and no cost, and the card marks the total
 * partial rather than printing a smaller number as though it were the whole. See
 * `telemetry/pricing.py`: prices are configuration, and the one shipped is the one
 * that could be sourced.
 */
export function Spend() {
  const t = useStrings();
  const spend = useConnection((s) => s.snapshot?.spend);
  if (!spend) return null;

  const { total, models, unattributed, cycles } = spend;
  const unpriced = models.filter((m) => m.cost_usd === null);
  const stray = unattributed.in + unattributed.out > 0;

  return (
    <div className="border border-line bg-panel">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-[9px]">
        <Icon d={ICON.committee} stroke={STROKE.amber} width={2.2} />
        <span className="font-mono text-[10px] font-bold leading-none tracking-[.12em] text-ink/60">
          {t.spend.title}
        </span>
        <span className="font-mono text-[10px] leading-none text-ink/30 tabular-nums">
          {t.spend.cycles(cycles)}
        </span>
        <span className="flex-1" />
        {/* The headline number, and the qualifier attached to it rather than
            printed underneath where it can be read separately. */}
        <span className="font-mono text-[13px] font-bold leading-none tabular-nums text-ink">
          {spend.partial ? t.spend.atLeast(money(spend.cost_usd)) : money(spend.cost_usd)}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-px bg-line">
        <Figure label={t.spend.tokensIn} value={plain(total.in, 0)} />
        <Figure label={t.spend.tokensOut} value={plain(total.out, 0)} />
        {/* Reported, and deliberately outside the arithmetic — Anthropic bills a
            cached read at a discount this project has no sourced figure for, and a
            guessed discount is a guess with a dollar sign in front of it. */}
        <Figure label={t.spend.cached} value={plain(total.cache_read, 0)}
                note={t.spend.cachedNote} />
      </div>

      <ul className="border-t border-line">
        {models.map((m) => (
          <li key={m.model}
              className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line-soft px-3 py-[7px] last:border-b-0">
            <span className="font-mono text-[11px] leading-none text-ink">{m.model}</span>
            <span className="font-mono text-[10px] leading-none tabular-nums text-ink/40">
              {t.spend.split(plain(m.in, 0), plain(m.out, 0))}
            </span>
            <span className="flex-1" />
            <span className={cn("font-mono text-[11px] font-semibold leading-none tabular-nums",
              m.cost_usd === null ? "text-ink/30" : "text-ink/75")}>
              {m.cost_usd === null ? t.spend.noPrice : money(m.cost_usd)}
            </span>
          </li>
        ))}
        {stray && (
          <li className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line-soft px-3 py-[7px] last:border-b-0">
            <span className="font-mono text-[11px] leading-none text-ink/45">
              {t.spend.unattributed}
            </span>
            <span className="font-mono text-[10px] leading-none tabular-nums text-ink/40">
              {t.spend.split(plain(unattributed.in, 0), plain(unattributed.out, 0))}
            </span>
            <span className="flex-1" />
            <span className="font-mono text-[11px] leading-none text-ink/30">
              {t.spend.noPrice}
            </span>
          </li>
        )}
      </ul>

      {unpriced.length > 0 && <Note>{t.spend.noPriceNote(unpriced[0]!.model)}</Note>}
      {stray && <Note>{t.spend.unattributedNote}</Note>}
    </div>
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
