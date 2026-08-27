import { cn } from "@/lib/cn";
import { clock } from "@/lib/format";
import { ICON } from "@/constants/icons";
import { CLS, STROKE } from "@/constants/theme";
import { Icon } from "@/components/Icon";
import { useCommittee } from "@/hooks/useCommittee";
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

  if (cards.length === 0) {
    return (
      <div className="mb-3 border border-edge bg-panel">
        <div className={CLS.empty}>{t.committee.empty}</div>
      </div>
    );
  }

  return (
    <div className="mb-3 flex flex-col gap-3">
      <div className="flex items-center gap-2 border border-line bg-panel px-3 py-[9px]">
        <Icon d={ICON.committee} stroke={STROKE.amber} width={2.2} />
        <span className="font-mono text-[10px] font-bold leading-none tracking-[.12em] text-ink/60">
          {t.committee.title}
        </span>
        <span className="font-sans text-[10.5px] leading-none text-ink/40">
          {t.committee.meta(cards.length)}
        </span>
      </div>

      {cards.map(({ key, session, verdict, gated, missing }) => (
        <article key={key} className="border border-edge bg-panel">
          <header className="flex items-center gap-[9px] border-b border-edge px-3 py-[9px]">
            <span className="font-mono text-[12px] font-bold leading-none text-ink">
              {session.underlying}
            </span>
            <span className="font-mono text-[10px] leading-none text-ink/40">
              {t.committee.headlines(session.headlines)}
            </span>
            <span className="flex-1" />
            <span className="font-mono text-[10px] font-bold leading-none tracking-[.1em]"
                  style={{ color: verdict.tone }}>
              {verdict.label}
            </span>
            <span className="font-mono text-[10px] leading-none text-ink/30">
              {clock(session.ts)}
            </span>
          </header>

          {/* 1. The catalyst: the one genuinely new input. */}
          <Stage label={t.committee.catalyst} tone={STROKE.agent}>
            {missing.catalyst ? (
              <Absent text={missing.catalyst} />
            ) : (
              <>
                <Lean lean={session.catalyst.lean} />
                <span className="text-ink/35">
                  {t.committee.confidence(session.catalyst.confidence?.toFixed(2) ?? "—")}
                </span>
                <p className="mt-[6px] w-full font-sans text-[12px] leading-[1.55] text-ink/65">
                  {session.catalyst.note}
                </p>
              </>
            )}
          </Stage>

          {/* 2. Side by side and at the same depth: they ran concurrently and
                 neither saw the other's case. */}
          <div className="grid gap-px border-b border-edge bg-edge sm:grid-cols-2">
            <Argument label={t.committee.bull} tone={STROKE.pass}
                      text={session.bull} absent={missing.bull} />
            <Argument label={t.committee.bear} tone={STROKE.fail}
                      text={session.bear} absent={missing.bear} />
          </div>

          {/* 3. Outcomes, not opinions — straight from the ledger. */}
          <Stage label={t.committee.reflection} tone={STROKE.muted}>
            {session.reflection.length === 0 ? (
              <span className="text-ink/35">{t.committee.reflectionEmpty}</span>
            ) : (
              <ul className="w-full">
                {session.reflection.map((r) => (
                  <li key={r.structure} className="font-mono text-[11px] leading-[1.5] text-ink/55">
                    {r.structure} — {r.realized_usd ?? "?"} ({r.outcome})
                  </li>
                ))}
              </ul>
            )}
          </Stage>

          {/* 4. The judge, and then the only thing that can actually stop it. */}
          <Stage label={t.committee.judge} tone={STROKE.amber} last>
            <div className="w-full">
              {session.outcome.error ? (
                <Absent text={session.outcome.error} />
              ) : (
                <p className="font-sans text-[12px] leading-[1.55] text-ink/65">
                  {session.outcome.structure && (
                    <span className="mr-2 font-mono text-[11px] font-semibold text-ink">
                      {session.outcome.structure}
                    </span>
                  )}
                  {session.outcome.rationale}
                </p>
              )}
              <div className="mt-[8px] flex flex-wrap items-center gap-2">
                <span className={cn("font-mono text-[10px] font-bold leading-none tracking-[.08em]",
                  gated === null ? "text-ink/30" : gated.ok ? "text-pass" : "text-fail")}>
                  {gated?.label ?? t.committee.ungated}
                </span>
                <span className="font-mono text-[10px] leading-none text-ink/25">
                  {t.committee.tokens(session.tokens.out ?? 0)}
                </span>
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

function Argument({ label, tone, text, absent }: {
  label: string; tone: string; text: string; absent: string | null;
}) {
  return (
    <div className="min-w-0 bg-panel px-3 py-[10px]">
      <div className="mb-[6px] font-mono text-[9px] font-bold leading-none tracking-[.12em]"
           style={{ color: tone }}>
        {label}
      </div>
      {absent ? <Absent text={absent} /> : (
        <p className="font-sans text-[12px] leading-[1.55] text-ink/65">{text}</p>
      )}
    </div>
  );
}

/** The catalyst's direction, coloured the way the rest of the panel colours a side. */
function Lean({ lean }: { lean: string }) {
  const tone = lean === "bullish" ? "text-pass"
    : lean === "bearish" ? "text-fail"
    : "text-ink/45";
  return (
    <span className={cn("font-mono text-[11px] font-bold leading-none tracking-[.06em]", tone)}>
      {lean.toUpperCase()}
    </span>
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
