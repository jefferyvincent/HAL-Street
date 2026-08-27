import { ICON } from "@/constants/icons";
import { CLS } from "@/constants/theme";
import { cn } from "@/lib/cn";
import { useSession } from "@/hooks/useSession";
import { Icon } from "./Icon";

/**
 * Which side of the bell we are on, from the broker's clock rather than this
 * machine's. Dashed when nothing has recorded a boundary yet — a `--once` run never
 * sees the market close, and a dash is honest where a guess would not be.
 */
export function SessionBell() {
  const { label, open, known, title } = useSession();
  return (
    <div
      title={title}
      className={cn(
        "flex items-center gap-[7px] border-l border-line px-3 font-mono text-[11px] font-semibold leading-none",
        !known ? "text-mute" : open ? "text-pass" : "text-mute",
      )}
    >
      <Icon d={ICON.bell} stroke="currentColor" />
      {known && <span className={cn(CLS.dot, open ? "bg-pass" : "bg-mute")} />}
      {label}
    </div>
  );
}
