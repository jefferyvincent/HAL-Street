import { cn } from "@/lib/cn";
import { ICON } from "@/constants/icons";
import { STROKE } from "@/constants/theme";
import { Icon } from "@/components/Icon";
import { usePresence } from "@/hooks/usePresence";

/**
 * Why the console is quiet, when it is quiet for a reason worth naming.
 *
 * Three of the five states get a line: a dropped connection, a shut market, and an
 * agent that has stopped writing during the session. Working and idle say nothing —
 * the panel is fine, and a banner announcing that is noise on a screen whose job is
 * to make the unusual visible.
 *
 * The order between them is `lib/presence`, and it is the design: a shut market
 * outranks a stale agent, because of course nothing has written for hours, and
 * reporting that as a stopped process would be a fault where there is none.
 */
export function Presence() {
  const { kind, message, tone } = usePresence();
  if (!message) return null;

  return (
    <div className={cn("flex items-start gap-[9px] border px-3 py-[9px]",
      "font-sans text-[11.5px] leading-[1.45]",
      kind === "disconnected" ? "border-fail/40 bg-fail/[.06]" : "border-line bg-panel",
      tone)}>
      <Icon d={kind === "closed" ? ICON.bell : ICON.shield} size={13}
            stroke={kind === "disconnected" ? STROKE.fail
                    : kind === "silent" ? STROKE.amber : STROKE.muted}
            width={2.2} />
      <span className="min-w-0">{message}</span>
    </div>
  );
}
