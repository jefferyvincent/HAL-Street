import { cn } from "@/lib/cn";
import { CLS, STROKE } from "@/constants/theme";
import { ICON } from "@/constants/icons";
import { Icon } from "@/components/Icon";
import { Ticker } from "@/components/Ticker";
import { useCommitteeRail } from "@/hooks/useCommitteeRail";
import { useStrings } from "@/hooks/useStrings";

/**
 * The committee arguing, in the corner of the eye.
 *
 * The full deliberation is its own tab. This is the shape of it beside whatever else
 * you are looking at: which name, what the catalyst read, whether both researchers
 * spoke, what the judge did, and what the gates did with it. The order is the order it
 * happened in, top to bottom, because the shape is the argument.
 *
 * It replaced a rail showing the gate families of whichever decision was selected and
 * a static list of limits — a meter that duplicated the decision record below it, and
 * numbers that now appear on the gates tab as live readings rather than a spec sheet.
 */
export function CommitteeRail() {
  const t = useStrings();
  const { card, live, elsewhere } = useCommitteeRail();

  return (
    <nav className="border-t border-line bg-sunk py-[10px] min-[1181px]:border-t-0 min-[1181px]:border-r">
      <div className="flex items-center gap-2 px-3 pb-[10px]">
        <Icon d={ICON.committee} stroke={STROKE.amber} width={2.2} />
        <span className="font-mono text-[9px] font-bold leading-none tracking-[.14em] text-ink/32">
          {t.committeeRail.title}
        </span>
        <span className="flex-1" />
        {live && (
          <span className={cn(CLS.dot, "animate-pulse bg-amber")} title={live.stage} />
        )}
      </div>

      {/* Said above the card, not on it. The agent works through the universe a name
          at a time, so by the time an argument is on screen it has usually moved on —
          and a live mark over a finished one would claim it is still being had. */}
      {elsewhere && (
        <div className="mx-[10px] mb-[10px] border border-line bg-panel px-[9px] py-[7px] font-mono text-[9.5px] leading-[1.4] text-amber/80">
          {elsewhere}
        </div>
      )}

      {!card ? (
        <div className="px-3 font-sans text-[11px] leading-[1.45] text-ink/30">
          {t.committee.empty}
        </div>
      ) : (
        <div className="mx-[10px] border border-line bg-panel">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-line px-[9px] py-[7px]">
            <Ticker symbol={card.underlying} />
            <span className="font-mono text-[9px] leading-none text-ink/30">
              {card.headlines}
            </span>
            <span className="flex-1" />
            <span className="font-mono text-[9px] leading-none text-ink/25">{card.ago}</span>
          </div>

          <Step label={t.committee.catalyst} tone={STROKE.agent}>
            {card.catalyst.lean ? (
              <span style={{ color: card.catalyst.lean.tone }}>{card.catalyst.lean.label}</span>
            ) : (
              <span className="text-fail/70">{card.catalyst.absent}</span>
            )}
          </Step>

          <div className="grid grid-cols-2 gap-px border-b border-line bg-line">
            <Side label={t.committee.bull} tone={STROKE.pass} absent={card.bull.absent} />
            <Side label={t.committee.bear} tone={STROKE.fail} absent={card.bear.absent} />
          </div>

          <Step label={t.committee.judge} tone={STROKE.amber}>
            <span style={{ color: card.verdict.tone }}>{card.verdict.label}</span>
          </Step>

          <div className="flex items-center gap-2 px-[9px] py-[7px]">
            <span className="w-[46px] shrink-0 font-mono text-[8.5px] font-bold leading-none tracking-[.1em] text-ink/30">
              {t.committeeRail.gates}
            </span>
            <span className={cn("font-mono text-[9px] font-bold leading-none tracking-[.06em]",
              card.gated === null ? "text-ink/25" : card.gated.ok ? "text-pass" : "text-fail")}>
              {card.gated?.label ?? t.committee.ungated}
            </span>
          </div>
        </div>
      )}
    </nav>
  );
}

function Step({ label, tone, children }: {
  label: string; tone: string; children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2 border-b border-line px-[9px] py-[7px]">
      <span className="w-[46px] shrink-0 font-mono text-[8.5px] font-bold leading-none tracking-[.1em]"
            style={{ color: tone }}>
        {label}
      </span>
      <span className="min-w-0 truncate font-mono text-[9px] font-bold leading-none tracking-[.06em]">
        {children}
      </span>
    </div>
  );
}

/** A researcher: whether they spoke, not what they said. The tab has what they said. */
function Side({ label, tone, absent }: { label: string; tone: string; absent: string | null }) {
  return (
    <div className="bg-panel px-[9px] py-[7px]">
      <div className="font-mono text-[8.5px] font-bold leading-none tracking-[.1em]"
           style={{ color: tone }}>
        {label}
      </div>
      <div className={cn("mt-[4px] font-mono text-[9px] leading-none",
        absent ? "text-fail/70" : "text-ink/45")}>
        {absent ? <Icon d={ICON.cross} size={9} stroke={STROKE.fail} />
                : <Icon d={ICON.tick} size={9} stroke={STROKE.pass} />}
      </div>
    </div>
  );
}
