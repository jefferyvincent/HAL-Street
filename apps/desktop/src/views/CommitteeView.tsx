import { cn } from "@/lib/cn";
import { ICON } from "@/constants/icons";
import { CLS, STROKE } from "@/constants/theme";
import { Icon } from "@/components/Icon";
import { Ticker } from "@/components/Ticker";
import { useCommittee, useCommitteeStatus, type Side } from "@/hooks/useCommittee";
import { useStrings } from "@/hooks/useStrings";

/**
 * How each proposal was reached: catalyst, then bull and bear in parallel, then a
 * judge.
 *
 * Drawn as a tree because the shape is the argument. The two researchers sit side
 * by side and at the same depth because they ran concurrently and neither saw the
 * other — a stacked list would imply one answered the other, which is exactly the
 * failure the parallel call exists to avoid. Everything converges on one judge,
 * and the judge converges on the gates, which is where the deliberation stops
 * mattering: more of it can make a better proposal, never a permitted one.
 */
export function CommitteeView() {
  const t = useStrings();
  const cards = useCommittee();
  const status = useCommitteeStatus();

  const header = (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border border-line bg-panel px-3 py-[9px]">
      <Icon d={ICON.committee} stroke={STROKE.amber} width={2.2} />
      <span className="font-mono text-[10px] font-bold leading-none tracking-[.12em] text-ink/60">
        {t.committee.title}
      </span>
      <span className="font-sans text-[10.5px] leading-none text-ink/40">
        {t.committee.meta(cards.length)}
      </span>
      <span className="flex-1" />
      {status.busy ? (
        <span className="flex items-center gap-[6px] font-mono text-[10px] font-bold leading-none tracking-[.08em] text-amber">
          <span className={cn(CLS.dot, "animate-pulse bg-amber")} />
          {status.label}
        </span>
      ) : (
        <span className="font-mono text-[10px] leading-none text-ink/25">
          {status.label}
        </span>
      )}
    </div>
  );

  if (cards.length === 0) {
    return (
      <div className="mb-3 flex flex-col gap-3">
        {header}
        <div className="border border-edge bg-panel">
          <div className={CLS.empty}>{t.committee.empty}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="mb-3 flex flex-col gap-3">
      {header}

      {cards.map((card, index) => (
        // Newest first, so index 0 is the one that just happened. Ringed rather than
        // merely labelled: the cards are otherwise identical at a glance, and "which
        // of these is new" was the question being asked.
        <article key={card.key}
                 className={cn("border bg-panel",
                   index === 0 ? "border-amber/60" : "border-edge")}>
          <header className="flex flex-wrap items-center gap-x-[9px] gap-y-1 border-b border-edge px-3 py-[9px]">
            <Ticker symbol={card.underlying} size="md" />
            {index === 0 && (
              <span className="font-mono text-[9px] font-bold leading-none tracking-[.12em] text-amber">
                {t.committee.latest}
              </span>
            )}
            <span className="font-mono text-[10px] leading-none text-ink/40">
              {card.headlines}
            </span>
            <span className="flex-1" />
            {/* The loud one. A deliberation that ended in an order is a different
                kind of event from one that ended in a decline, and it was reading
                as one more grey word at the bottom of the card. */}
            {card.gated?.ok && (
              <span className="border border-pass/50 px-[6px] py-[3px] font-mono text-[9px] font-bold leading-none tracking-[.1em] text-pass">
                {t.committee.ordered}
              </span>
            )}
            <span className="font-mono text-[10px] font-bold leading-none tracking-[.1em]"
                  style={{ color: card.verdict.tone }}>
              {card.verdict.label}
            </span>
            {/* Both, because they answer different questions: "when" and "how long
                ago". A wall clock alone makes a card from two hours back look as
                current as one from two minutes back. */}
            <span className="font-mono text-[10px] leading-none text-ink/30 tabular-nums">
              {card.time}
            </span>
            <span className="font-mono text-[10px] leading-none text-ink/25">
              {card.ago}
            </span>
          </header>

          {/* 1. The catalyst: the one genuinely new input. */}
          <Stage label={t.committee.catalyst} tone={STROKE.agent}>
            {card.catalyst.absent ? (
              <Absent text={card.catalyst.absent} />
            ) : (
              <>
                {card.catalyst.lean && (
                  <span className={cn("font-mono text-[11px] font-bold leading-none tracking-[.06em]",
                    card.catalyst.lean.tone)}>
                    {card.catalyst.lean.label}
                  </span>
                )}
                <span className="text-ink/35">{card.catalyst.confidence}</span>
                <p className="mt-[6px] w-full font-sans text-[12px] leading-[1.55] text-ink/65">
                  {card.catalyst.note}
                </p>
              </>
            )}
          </Stage>

          {/* 2. Side by side and at the same depth: they ran concurrently and
                 neither saw the other's case. */}
          <div className="grid gap-px border-b border-edge bg-edge sm:grid-cols-2">
            <Argument label={t.committee.bull} tone={STROKE.pass} side={card.bull} />
            <Argument label={t.committee.bear} tone={STROKE.fail} side={card.bear} />
          </div>

          {/* 3. Outcomes, not opinions — straight from the ledger. */}
          <Stage label={t.committee.reflection} tone={STROKE.muted}>
            {card.reflection.length === 0 ? (
              <span className="text-ink/35">{t.committee.reflectionEmpty}</span>
            ) : (
              <ul className="w-full">
                {card.reflection.map((r) => (
                  <li key={r.key} className="font-mono text-[11px] leading-[1.5] text-ink/55">
                    {r.text}
                  </li>
                ))}
              </ul>
            )}
          </Stage>

          {/* 4. The judge, and then the only thing that can actually stop it. */}
          <Stage label={t.committee.judge} tone={STROKE.amber}>
            <div className="w-full">
              {card.judge.error ? (
                <Absent text={card.judge.error} />
              ) : (
                <p className="font-sans text-[12px] leading-[1.55] text-ink/65">
                  {card.judge.structure && (
                    <span className="mr-2 font-mono text-[11px] font-semibold text-ink">
                      {card.judge.structure}
                    </span>
                  )}
                  {card.judge.rationale}
                </p>
              )}
              <div className="mt-[8px] flex flex-wrap items-center gap-2">
                <span className={cn("font-mono text-[10px] font-bold leading-none tracking-[.08em]",
                  card.gated === null ? "text-ink/30" : card.gated.ok ? "text-pass" : "text-fail")}>
                  {card.judge.outcome}
                </span>
                <span className="font-mono text-[10px] leading-none text-ink/25">
                  {card.judge.tokens}
                </span>
              </div>
            </div>
          </Stage>

          {/* Where the tokens went, and which model spent them. A single total said
              the committee was expensive without saying which quarter of it to look
              at — and now that the three research stages run a tier below the judge,
              a total has no price at all. */}
          <Stage label={t.committee.cost} tone={STROKE.muted} last>
            <div className="w-full">
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                {card.stages.map((s) => (
                  <span key={s.key} className="font-mono text-[10px] leading-none text-ink/45 tabular-nums">
                    <span className="text-ink/70">{s.stage}</span>{" "}
                    {s.spend}
                    {s.model && (
                      <span className="text-ink/25"> {t.committee.stageModel(s.model)}</span>
                    )}
                  </span>
                ))}
              </div>
              <div className="mt-[6px] font-sans text-[10.5px] leading-[1.45] text-ink/30">
                {t.committee.costNote}
              </div>
            </div>
          </Stage>

          <div className="flex gap-[7px] border-t border-edge px-3 py-2 font-sans text-[10.5px] leading-[1.45] text-ink/40">
            <Icon d={ICON.shield} size={12} stroke={STROKE.muted} width={2.2} />
            <span>{t.committee.note}</span>
          </div>
        </article>
      ))}
    </div>
  );
}

function Stage({ label, tone, children, last = false }: {
  label: string; tone: string; children: React.ReactNode; last?: boolean;
}) {
  return (
    <div className={cn("flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3 py-[10px]",
      !last && "border-b border-edge")}>
      <span className="w-[76px] shrink-0 font-mono text-[9px] font-bold leading-none tracking-[.12em]"
            style={{ color: tone }}>
        {label}
      </span>
      {children}
    </div>
  );
}

function Argument({ label, tone, side }: { label: string; tone: string; side: Side }) {
  return (
    <div className="min-w-0 bg-panel px-3 py-[10px]">
      <div className="mb-[6px] font-mono text-[9px] font-bold leading-none tracking-[.12em]"
           style={{ color: tone }}>
        {label}
      </div>
      {side.absent ? <Absent text={side.absent} /> : (
        <p className="font-sans text-[12px] leading-[1.55] text-ink/65">{side.text}</p>
      )}
    </div>
  );
}

/** A stage that did not answer, said so rather than drawn blank.
 *
 * An empty arm and a missing arm look identical otherwise, and they are different
 * facts: a missing researcher means the judge decided having heard one side. */
function Absent({ text }: { text: string }) {
  return (
    <span className="font-mono text-[11px] leading-[1.5] text-fail/70">{text}</span>
  );
}
