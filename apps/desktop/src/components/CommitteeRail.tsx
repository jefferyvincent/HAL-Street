import { cn } from "@/lib/cn";
import { CLS, STROKE } from "@/constants/theme";
import { ICON } from "@/constants/icons";
import { Icon } from "@/components/Icon";
import { LiveStages } from "@/components/LiveCommittee";
import { Ticker } from "@/components/Ticker";
import { useCommitteeRail, type RailRow } from "@/hooks/useCommitteeRail";
import { useStrings } from "@/hooks/useStrings";

/**
 * What the desk is doing, and the deliberations behind it.
 *
 * The state line is always there — offline, market closed with the next open, the
 * stage running now, or between cycles. A rail that only speaks when something is
 * happening is indistinguishable from a broken one when nothing is, which is exactly
 * how it read after hours.
 *
 * Below it, the recent deliberations rather than the newest alone: one line each,
 * newest first, with a live mark on the one actually being argued. The full argument
 * — catalyst, both cases, the judge's reasoning — is the tab, which is the archive.
 * This is the stream, and it says how many are only there.
 */
export function CommitteeRail() {
  const t = useStrings();
  const { state, stateTone, detail, rows, hidden, empty, openArchive } = useCommitteeRail();

  return (
    <nav className="border-t border-line bg-sunk py-[10px] min-[1181px]:border-t-0 min-[1181px]:border-r">
      <div className="flex items-center gap-2 px-3 pb-[9px]">
        <Icon d={ICON.committee} stroke={STROKE.amber} width={2.2} />
        <span className="font-mono text-[9px] font-bold leading-none tracking-[.14em] text-ink/32">
          {t.committeeRail.title}
        </span>
      </div>

      {/* Always something. This is the half that was missing. */}
      <div className="mx-[10px] mb-[10px] border border-line bg-panel px-[9px] py-[8px]">
        <div className={cn("font-mono text-[9.5px] font-bold leading-none tracking-[.1em]",
          stateTone)}>
          {state}
        </div>
        {detail && (
          <div className="mt-[5px] font-mono text-[9px] leading-none text-ink/30">{detail}</div>
        )}
        {/* Which of the four calls the desk is on. Silent unless a committee is
            actually sitting — see `lib/liveSession` for why that is not the same
            as "a cycle is running". */}
        <LiveStages />
      </div>

      {rows.length === 0 ? (
        <div className="px-3 font-sans text-[11px] leading-[1.45] text-ink/30">{empty}</div>
      ) : (
        <div className="mx-[10px] border border-line bg-panel">
          {rows.map((r) => <Row key={r.key} row={r} />)}
        </div>
      )}

      {hidden > 0 && (
        <button
          onClick={openArchive}
          className={cn("mx-[10px] mt-[9px] flex w-[calc(100%-20px)] items-center gap-[6px]",
            "border border-line bg-panel px-[9px] py-[7px] font-mono text-[9px]",
            "leading-none tracking-[.06em] text-ink/40",
            "transition-colors hover:text-ink focus-visible:outline",
            "focus-visible:outline-1 focus-visible:outline-amber")}
        >
          <Icon d={ICON.committee} size={10} stroke="currentColor" />
          {t.committeeRail.more(hidden)}
        </button>
      )}
    </nav>
  );
}

/** One deliberation: which name, what the tape said, what came of it. */
function Row({ row }: { row: RailRow }) {
  return (
    <div className="flex flex-wrap items-center gap-x-[6px] gap-y-1 border-b border-line-soft px-[9px] py-[7px] last:border-b-0">
      {row.live && <span className={cn(CLS.dot, "animate-pulse bg-amber")} />}
      <Ticker symbol={row.underlying} />
      {row.lean && (
        <span className="font-mono text-[8.5px] font-bold leading-none tracking-[.06em]"
              style={{ color: row.lean.tone }}>
          {row.lean.label}
        </span>
      )}
      <span className="flex-1" />
      <span className="font-mono text-[9px] leading-none text-ink/25">{row.ago}</span>
      <span className="w-full font-mono text-[8.5px] font-bold leading-none tracking-[.08em]"
            style={{ color: row.gated ? undefined : row.verdict.tone }}>
        {row.gated
          ? <span className={row.gated.ok ? "text-pass" : "text-fail"}>{row.gated.label}</span>
          : row.verdict.label}
      </span>
    </div>
  );
}
