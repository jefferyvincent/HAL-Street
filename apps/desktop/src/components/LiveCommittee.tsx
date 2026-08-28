import { cn } from "@/lib/cn";
import { CLS, STROKE } from "@/constants/theme";
import { ICON } from "@/constants/icons";
import { Icon } from "@/components/Icon";
import { Ticker } from "@/components/Ticker";
import { useLiveCommittee, type LiveSession, type LiveStageRow } from "@/hooks/useLiveCommittee";

/**
 * The argument being had right now, filling in as it is had.
 *
 * The tab was an archive and only an archive: a card appeared when the judge returned,
 * so the four model calls before it — the slowest and most interesting minute of a
 * cycle — showed the previous session under one unchanging amber word. This is the
 * same session before it is finished, and it disappears when the real one lands.
 *
 * It renders nothing at all when nothing is running. That is not an empty state to be
 * filled: the agent scans on a cadence, a cycle is a minute of every thirty, and the
 * archive underneath is exactly what a quiet panel should be showing.
 */
export function LiveCommittee() {
  const live = useLiveCommittee();
  if (!live) return null;

  return (
    <article className="border border-amber/50 bg-panel">
      <Header live={live} />
      {live.rows.length > 0 && (
        <>
          <ul>
            {live.rows.map((row) => (
              <Stage key={row.key} row={row} word={live.stateWord[row.state]} />
            ))}
          </ul>
          <div className="border-t border-edge px-3 py-[7px] font-sans text-[10.5px] leading-[1.45] text-ink/30">
            {live.note}
          </div>
        </>
      )}
    </article>
  );
}

/** Which name, and the stage in the agent's own words. */
function Header({ live }: { live: LiveSession }) {
  return (
    <header className="flex flex-wrap items-center gap-x-[9px] gap-y-1 border-b border-edge px-3 py-[9px]">
      <Icon d={ICON.committee} stroke={STROKE.amber} width={2.2} />
      <span className="font-mono text-[9px] font-bold leading-none tracking-[.14em] text-amber">
        {live.title}
      </span>
      <Ticker symbol={live.underlying} />
      <span className="flex-1" />
      <span className="flex items-center gap-[6px] font-mono text-[10px] font-bold leading-none tracking-[.08em] text-amber">
        <span className={cn(CLS.dot, "animate-pulse bg-amber")} />
        {live.stage}
      </span>
    </header>
  );
}

/**
 * One stage, and whatever it has produced.
 *
 * The three are always drawn, including the ones that have not started, because the
 * shape of the deliberation is the point: a reader watching "BULL & BEAR working"
 * knows a judge is still to come. A list that grew a row at a time would say the
 * session was over every time it paused.
 */
function Stage({ row, word }: { row: LiveStageRow; word: string }) {
  const tone = row.state === "running" ? "text-amber"
    : row.state === "done" ? "text-ink/55"
    : "text-ink/25";

  return (
    <li className="flex flex-wrap items-baseline gap-x-[10px] gap-y-1 border-b border-edge px-3 py-[7px] last:border-b-0">
      <span className={cn("w-[86px] shrink-0 font-mono text-[9px] font-bold leading-none tracking-[.12em]",
        tone)}>
        {row.label}
      </span>
      <span className={cn("flex items-center gap-[6px] font-mono text-[10px] leading-none", tone)}>
        {row.state === "running" && <span className={cn(CLS.dot, "animate-pulse bg-amber")} />}
        {word}
      </span>
      {row.detail && (
        <span className="min-w-0 font-sans text-[11px] leading-[1.4] text-ink/60">
          {row.detail}
        </span>
      )}
    </li>
  );
}

/**
 * The same progression, compact, for the 200px rail beside the console.
 *
 * Three words and a dot: enough to see which of the four calls the desk is on without
 * turning the rail into the thing you are reading. The tab is where the argument goes.
 */
export function LiveStages() {
  const live = useLiveCommittee();
  if (!live || live.rows.length === 0) return null;

  return (
    <ul className="mt-[7px] flex flex-col gap-[4px]">
      {live.rows.map((row) => (
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
