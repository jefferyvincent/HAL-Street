import { cn } from "@/lib/cn";
import { CLS, STROKE } from "@/constants/theme";
import { ICON } from "@/constants/icons";
import { Icon } from "@/components/Icon";
import { Brief } from "@/components/Brief";
import { Ticker } from "@/components/Ticker";
import { useCommitteeDesk, type DeskRow } from "@/hooks/useCommitteeDesk";
import { useStrings } from "@/hooks/useStrings";

/**
 * Who is at the desk, and what each of them has said.
 *
 * The shape is HAL's cognition roster: a fixed list of members in the order they
 * speak, a dot each, and their verdict written in as it lands. What it replaced was a
 * stack of finished cards, newest first — so the tab was mostly deliberations from
 * five and eighteen hours ago, and the one actually happening was a word in a header.
 *
 * All five seats, always, including the ones still to come. The shape of the argument
 * is the point: a reader watching BULL and BEAR working knows a head trader is next
 * and the gates are after that. A list that grew a row at a time would say the
 * session was over every time it paused.
 *
 * Live or not is stated, not implied — a pulsing header and a stage, against a flat
 * one saying how long ago the desk rose. Which of the two it is decides everything
 * below it, and `useCommitteeDesk` decides that once.
 */
export function CommitteeDesk() {
  const t = useStrings();
  const desk = useCommitteeDesk();

  return (
    <div className="flex flex-col gap-3">
      {/* First, because it is first. The menu is built by the gates' own arithmetic
          and journalled a stage before the committee sits, so it is on screen for the
          whole of the minute that used to show nothing — and reading four paragraphs
          of argument before seeing what was being argued about is the wrong order
          however long the page is. */}
      <Brief underlying={desk.underlying} live={desk.live} />

      <article className={cn("border bg-panel", desk.live ? "border-amber/60" : "border-edge")}>
      <header className="flex flex-wrap items-center gap-x-[9px] gap-y-1 border-b border-edge px-3 py-[9px]">
        <Icon d={ICON.committee} stroke={desk.live ? STROKE.amber : STROKE.muted} width={2.2} />
        <span className={cn("font-mono text-[9px] font-bold leading-none tracking-[.14em]",
          desk.live ? "text-amber" : "text-ink/40")}>
          {t.committee.desk.title}
        </span>
        {desk.underlying && <Ticker symbol={desk.underlying} />}
        <span className="flex-1" />
        {desk.status && (
          <span className={cn("flex items-center gap-[6px] font-mono text-[10px] leading-none",
            desk.live ? "font-bold tracking-[.08em] text-amber" : "text-ink/30")}>
            {desk.live && <span className={cn(CLS.dot, "animate-pulse bg-amber")} />}
            {desk.status}
          </span>
        )}
      </header>

      {desk.empty ? (
        <div className={CLS.empty}>{desk.empty}</div>
      ) : (
        <ul>
          {desk.rows.map((row) => <Seat key={row.key} row={row} />)}
        </ul>
      )}

      {desk.note && (
        <div className="border-t border-edge px-3 py-[7px] font-sans text-[10.5px] leading-[1.45] text-ink/30">
          {desk.note}
        </div>
      )}
      </article>
    </div>
  );
}

/**
 * One seat: where it is, and what it said.
 *
 * `absent` is drawn in the failure colour and carries its reason rather than being
 * left blank. A researcher that did not answer means the head trader decided having
 * heard one side, which is a fact about the decision and not a gap in the display.
 */
function Seat({ row }: { row: DeskRow }) {
  const tone = row.state === "working" ? "text-amber"
    : row.state === "in" ? "text-ink/60"
    : row.state === "absent" ? "text-fail/70"
    : "text-ink/25";

  const dot = row.state === "working" ? "animate-pulse bg-amber"
    : row.state === "in" ? "bg-amber/60"
    : row.state === "absent" ? "bg-fail/60"
    : "bg-ink/15";

  return (
    <li className="flex gap-[10px] border-b border-edge px-3 py-[9px] last:border-b-0">
      <span className={cn(CLS.dot, "mt-[5px] shrink-0", dot)} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-[9px] gap-y-1">
          <span className={cn("font-mono text-[9px] font-bold leading-none tracking-[.12em]", tone)}>
            {row.label}
          </span>
          <span className={cn("font-mono text-[9.5px] leading-none", tone)}>{row.word}</span>
        </div>
        {row.text && (
          <p className="mt-[5px] font-sans text-[11.5px] leading-[1.5] text-ink/65">
            {row.text}
          </p>
        )}
        {/* Said about the text, not by it. A case whose tail the record dropped ends
            mid-thought, and without this line that reads as the researcher trailing
            off — or as a fault in this component. */}
        {row.footnote && (
          <p className="mt-[4px] font-mono text-[9px] leading-[1.4] text-ink/25">
            {row.footnote}
          </p>
        )}
      </div>
    </li>
  );
}
