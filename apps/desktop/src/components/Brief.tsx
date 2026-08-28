import { cn } from "@/lib/cn";
import { CLS, STROKE } from "@/constants/theme";
import { ICON } from "@/constants/icons";
import { Icon } from "@/components/Icon";
import { useBrief, type BriefLine } from "@/hooks/useBrief";
import { useStrings } from "@/hooks/useStrings";

/**
 * What the committee was given, above what it said about it.
 *
 * The tab drew the argument and never the thing being argued about. Every structure
 * on this list was built by the gates' own arithmetic, scored, and written to the
 * journal before anybody deliberated — and none of it had ever been on a screen. Four
 * paragraphs of reasoning about an invisible menu is how a full tab reads as dead.
 *
 * It is also the half that arrives first. The menu lands a stage before the committee
 * sits, so this is on screen for the whole of the minute that used to show nothing.
 *
 * `fit` is the deterministic verdict — paid for the direction the tape was read to
 * have, needing the opposite, or ambient because none was earned. It comes from
 * `strategy/burn.py` and is never recomputed here; a structure nobody has scored says
 * so rather than borrowing the word for "no direction earned".
 */
export function Brief({ underlying, live }: { underlying: string; live: boolean }) {
  const t = useStrings();
  const brief = useBrief(underlying, live);
  if (!brief) return null;

  return (
    <article className="border border-edge bg-panel">
      <header className="flex flex-wrap items-center gap-x-[9px] gap-y-1 border-b border-edge px-3 py-[9px]">
        <Icon d={ICON.list} stroke={STROKE.muted} width={2.2} />
        <span className="font-mono text-[9px] font-bold leading-none tracking-[.14em] text-ink/40">
          {t.committee.brief.title}
        </span>
        <span className="font-sans text-[10.5px] leading-none text-ink/35">{brief.meta}</span>
        <span className="flex-1" />
        {brief.signal && (
          <span className="font-mono text-[9.5px] leading-none text-ink/40">{brief.signal}</span>
        )}
      </header>

      {/* The one sentence that is about the *pair* of reads rather than either of
          them. When they disagree it is the whole reason a directional structure is
          not on the table, and it was only ever visible inside the judge's prose. */}
      {/* What the daily chain makes of direction here, and — the half that matters —
          whether that read reaches as far as the structures below it. On every name
          measured so far it does not, and saying so is the contribution: a chain
          informative for two days is not an argument about a 49-day hold. */}
      {brief.persistence && (
        <div className="flex flex-wrap items-baseline gap-x-[9px] gap-y-1 border-b border-edge px-3 py-[7px]">
          <span className="font-mono text-[9.5px] leading-none text-ink/45">
            {brief.persistence.text}
          </span>
          <span className={cn("font-mono text-[9px] leading-none",
            brief.persistence.inReach ? "text-ink/35" : "text-ink/25 italic")}>
            {brief.persistence.reach}
          </span>
        </div>
      )}

      {brief.note && (
        <p className="border-b border-edge px-3 py-[8px] font-sans text-[11px] leading-[1.5] text-ink/45">
          {brief.note}
        </p>
      )}

      {brief.empty ? (
        <div className={CLS.empty}>{brief.empty}</div>
      ) : (
        <ul>
          {brief.rows.map((row) => <Structure key={row.key} row={row} />)}
        </ul>
      )}

      <div className="border-t border-edge px-3 py-[7px] font-sans text-[10.5px] leading-[1.45] text-ink/25">
        {t.committee.brief.note}
      </div>
    </article>
  );
}

/** One structure: the verdict the arithmetic reached, its name, and its numbers. */
function Structure({ row }: { row: BriefLine }) {
  return (
    <li className="border-b border-edge px-3 py-[9px] last:border-b-0">
      <div className="flex flex-wrap items-center gap-x-[9px] gap-y-1">
        <span className={cn("shrink-0 border px-[5px] py-[2px] font-mono text-[8.5px]",
          "font-bold leading-none tracking-[.1em]", row.fitTone)}>
          {row.fit}
        </span>
        <span className="min-w-0 font-mono text-[11.5px] font-semibold leading-[1.3] text-ink">
          {row.name}
        </span>
        <span className="flex-1" />
        {row.facts.map((fact) => (
          <span key={fact} className="shrink-0 font-mono text-[9.5px] leading-none tabular-nums text-ink/35">
            {fact}
          </span>
        ))}
      </div>
      {row.why && (
        <p className="mt-[5px] font-sans text-[11px] leading-[1.45] text-ink/45">{row.why}</p>
      )}
      {/* What twenty thousand sampled paths make of it, after the round trip. The
          expectation is the number every decline this week has actually been about,
          and it was being reached in prose because nothing computed it. */}
      <div className="mt-[5px] flex flex-wrap items-baseline gap-x-[10px] gap-y-1">
        {row.ev && (
          <span className={cn("font-mono text-[10px] font-bold leading-none tabular-nums",
            row.evUp ? "text-pass" : "text-fail")}>
            {row.ev}
          </span>
        )}
        <span className="font-mono text-[9.5px] leading-none text-ink/30">{row.tail}</span>
      </div>
    </li>
  );
}
