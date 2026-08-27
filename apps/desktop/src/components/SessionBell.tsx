import { ICON } from "@/constants/icons";
import { CLS } from "@/constants/theme";
import { cn } from "@/lib/cn";
import { useSession } from "@/hooks/useSession";
import { Icon } from "./Icon";

/**
 * Which side of the bell we are on, from the broker's clock rather than this
 * machine's. Dashed when nothing has recorded a boundary yet — a `--once` run never
 * sees the market close, and a dash is honest where a guess would not be.
 *
 * `certain` is separate from `open`. A close the agent never wrote down but the
 * broker had already published is a fact, and reads as one; the only hedged case is
 * the one where nothing is writing and no boundary has passed to reason from.
 */
export function SessionBell() {
  const { label, open, known, certain, title } = useSession();
  return (
    <div
      title={title}
      className={cn(
        "flex shrink-0 items-center gap-[7px] border-l border-line px-3 font-mono text-[11px] font-semibold leading-none",
        !known || !certain ? "text-mute" : open ? "text-pass" : "text-mute",
      )}
    >
      <Icon d={ICON.bell} stroke="currentColor" />
      {known && certain && <span className={cn(CLS.dot, open ? "bg-pass" : "bg-mute")} />}
      {label}
      {/* Said once, quietly, rather than folded into the label. "CLOSED" is the
          answer; whether anyone was there to see it happen is a footnote. */}
      {known && !certain && <span className="text-mute/60">?</span>}
    </div>
  );
}
