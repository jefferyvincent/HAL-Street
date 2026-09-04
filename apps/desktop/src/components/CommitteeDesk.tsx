import { cn } from "@/lib/cn";
import { CLS, STROKE } from "@/constants/theme";
import { ICON } from "@/constants/icons";
import { Icon } from "@/components/Icon";
import { Brief } from "@/components/Brief";
import { Ticker } from "@/components/Ticker";
import { useCommitteeDesk, type DeskRow } from "@/hooks/useCommitteeDesk";
import { useStrings } from "@/hooks/useStrings";

/**
 * Who is at the desk right now — and nothing at all when nobody is.
 *
 * The shape is HAL's cognition roster: members in the order they speak, a dot each, a
 * bar filling toward the final call, and a clock that moves. What it will not do is
 * what it used to: fall back to the last finished session and draw a deliberation from
 * five hours ago in the present tense, as the lead item, on the tab whose job is to
 * say what is happening now. Finished sessions are archive.
 *
 * All five seats while it sits, including the ones still to come — the shape of the
 * argument is the point, and a reader watching BULL and BEAR working knows a head
 * trader is next and the gates are after that.
 */
export function CommitteeDesk() {
  const desk = useCommitteeDesk();

  if (!desk.sitting) return <Idle desk={desk} />;

  return (
    <div className="flex flex-col gap-3">
      {/* First, because it is first. The menu is built by the gates' own arithmetic
          and journalled a stage before the committee sits. */}
      <Brief underlying={desk.underlying} live />

      <article className="border border-amber/60 bg-panel">
        <header className="flex flex-wrap items-center gap-x-[9px] gap-y-1 border-b border-edge px-3 py-[9px]">
          <Icon d={ICON.committee} stroke={STROKE.amber} width={2.2} />
          <span className="font-mono text-[9px] font-bold leading-none tracking-[.14em] text-amber">
            {useStrings().committee.desk.title}
          </span>
          <Ticker symbol={desk.underlying} />
          <span className="flex-1" />
          <span className="flex items-center gap-[6px] font-mono text-[10px] font-bold leading-none tracking-[.08em] text-amber">
            <span className={cn(CLS.dot, "desk-dot bg-amber")} />
            {desk.stage}
          </span>
          {desk.clock && (
            <span className="font-mono text-[9.5px] leading-none tabular-nums text-ink/35">
              {desk.clock}
            </span>
          )}
        </header>

        {/* How far along, the way HAL draws it. Transitioned rather than snapped: a
            bar that jumps a fifth every twenty seconds reads as a redraw, and the
            movement is the only thing on screen saying the wait is finite. */}
        <div className="h-[2px] w-full bg-line">
          <div className="h-full bg-amber transition-[width] duration-500 ease-out"
               style={{ width: `${Math.round(desk.progress * 100)}%` }} />
        </div>

        <ul>
          {desk.rows.map((row) => <Seat key={row.key} row={row} />)}
        </ul>

        <div className="border-t border-edge px-3 py-[7px] font-sans text-[10.5px] leading-[1.45] text-ink/30">
          {desk.note}
        </div>
      </article>
    </div>
  );
}

/**
 * Why there is no desk — never merely that there is none.
 *
 * Four reasons, and they call for opposite reactions: a dropped socket is worth fixing
 * now, a shut market is worth ignoring until morning, a silent agent during the session
 * is the one that should worry somebody, and between scans is simply the answer. The
 * order between them is `lib/presence`.
 */
function Idle({ desk }: { desk: ReturnType<typeof useCommitteeDesk> }) {
  if (!desk.idle) return null;

  return (
    <article className="border border-edge bg-panel">
      <header className="flex items-center gap-[9px] border-b border-edge px-3 py-[9px]">
        <Icon d={ICON.committee} stroke={STROKE.muted} width={2.2} />
        <span className={cn("font-mono text-[9px] font-bold leading-none tracking-[.14em]",
          desk.idle.tone)}>
          {desk.idle.title}
        </span>
        <span className="flex-1" />
        <span className="font-mono text-[9.5px] leading-none text-ink/25">{desk.archived}</span>
      </header>
      {/* No note under this one. "Written as it happens" is about a desk that is
          sitting, and printing it over a panel that says nothing is happening is the
          screen contradicting itself in two lines. */}
      <p className="px-3 py-[10px] font-sans text-[11.5px] leading-[1.5] text-ink/40">
        {desk.idle.detail}
      </p>
    </article>
  );
}

/** One seat: where it is, and what it said. */
function Seat({ row }: { row: DeskRow }) {
  const working = row.state === "working";
  const tone = working ? "text-amber"
    : row.state === "in" ? "text-ink/60"
    : row.state === "absent" ? "text-fail/70"
    : "text-ink/25";

  return (
    <li className={cn("flex gap-[10px] border-b border-edge px-3 py-[9px] last:border-b-0",
      working && "desk-busy")}>
      <span className={cn(CLS.dot, "mt-[5px] shrink-0",
        working ? "desk-dot bg-amber"
          : row.state === "in" ? "bg-amber/60"
          : row.state === "absent" ? "bg-fail/60"
          : "bg-ink/15")} />
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
      </div>
    </li>
  );
}
