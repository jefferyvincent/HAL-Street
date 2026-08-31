import { cn } from "@/lib/cn";
import { CLS } from "@/constants/theme";
import { useStrings } from "@/hooks/useStrings";
import { usePatternRead } from "@/hooks/usePatternRead";
import type { Position } from "@/types";

/**
 * What the chart is doing, beside a position that is already on.
 *
 * Informational by construction — there is nothing to click and nothing it can
 * change. The exit policy is arithmetic over the mark and the calendar, and it does
 * not read a word of this; the point is that a human watching an unattended agent
 * can see a bearish reversal forming under a bullish spread without having to open
 * a chart somewhere else.
 */
export function PatternBadge({ position }: { position: Position }) {
  const t = useStrings();
  const read = usePatternRead(position);
  const against = position.against?.length ?? 0;
  const confirming = position.confirming?.length ?? 0;

  return (
    <div className="flex flex-col gap-[3px]" title={read.title}>
      <div className="flex items-center gap-[7px] font-mono text-[10px] font-semibold leading-none">
        <span style={{ color: read.tone }}>{read.exposure}</span>
        {against > 0 && (
          <span className={cn(CLS.dot, "bg-fail")} aria-hidden />
        )}
        {against > 0 && <span className="text-fail">{t.book.against(against)}</span>}
        {against === 0 && confirming > 0 && (
          <span className="text-pass">{t.book.confirming(confirming)}</span>
        )}
      </div>
      {/* The chart read goes underneath, always — including when it found nothing.
          These are two independent facts: what the position needs the tape to do, and
          whether any confirmed pattern is on the chart. Run together on one line they
          read as a single garbled sentence: "WANTS THE MARKET UP no pattern on the
          chart", which is how it was reported. */}
      {read.quiet && (
        <span className="font-mono text-[10px] leading-none text-muted">
          {t.book.patternsNone}
        </span>
      )}
      {read.lines.length > 0 && (
        <ul className="flex flex-col gap-[2px]">
          {read.lines.map((l) => (
            <li key={l.key} className="font-mono text-[10px] leading-none"
                style={{ color: l.tone }}>
              {l.text}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
