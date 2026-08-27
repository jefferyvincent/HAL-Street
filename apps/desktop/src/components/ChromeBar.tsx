import { cn } from "@/lib/cn";
import { money } from "@/lib/format";
import { ICON } from "@/constants/icons";
import { CLS, STROKE } from "@/constants/theme";
import { useStrings } from "@/hooks/useStrings";
import { useTabs } from "@/hooks/useTabs";
import { useConnection } from "@/stores/connection";
import { Icon } from "./Icon";
import { SessionBell } from "./SessionBell";
import { SoundToggle } from "./SoundToggle";

export function ChromeBar() {
  const t = useStrings();
  const { tabs, go } = useTabs();
  const busy = useConnection((s) => s.snapshot?.in_flight) ?? null;
  const armed = useConnection((s) => s.snapshot?.armed) ?? null;
  const snap = useConnection((s) => s.snapshot);
  const halted = snap?.circuit.halted ?? false;

  return (
    // Wraps rather than squeezes. The first attempt at this pinned every status chip
    // and left the tab strip as the only flexible thing, which inverted the priority:
    // on a narrow window the six chips held their width and the tabs — the actual
    // navigation — were crushed into a sliver. Nothing shrinks now; the status group
    // drops to a second line when the row runs out, and the bar grows by 34px.
    <div className="sticky top-0 z-10 flex min-h-[34px] flex-wrap items-stretch border-b border-line bg-chrome">
      <div className="flex h-full shrink-0 items-center gap-[7px] bg-amber px-[14px]">
        <Icon d={ICON.hal} size={14} stroke={STROKE.void} width={2.2} />
        <span className="font-mono text-[12px] font-bold leading-none tracking-[.06em] text-void">
          {t.chrome.brand}
        </span>
      </div>

      {/* Navigation outranks status. These never shrink and never scroll. */}
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => go(tab.id)}
          className={cn(CLS.tab, "min-h-[34px] shrink-0", tab.active ? CLS.tabOn : CLS.tabOff)}
        >
          <Icon d={tab.icon} stroke={tab.active ? STROKE.amber : "currentColor"} />
          {t.tabs[tab.id]}
          {tab.count !== null && <span className="tabular-nums">{tab.count}</span>}
        </button>
      ))}

      {/* One group, so the chips wrap together to the next line rather than three
          going over and three staying behind. `flex-1` takes the slack so they sit
          right while they fit, and `justify-end` keeps them there afterwards. */}
      <div className="flex min-h-[34px] flex-1 flex-wrap items-center justify-end">
        <div className={cn("flex shrink-0 items-center gap-[7px] border-l border-line px-3 font-mono text-[11px] font-semibold leading-none",
          halted ? "text-fail" : "text-pass")}>
          <span className={cn(CLS.dot, halted ? "bg-fail" : "bg-pass")} />
          {halted ? t.chrome.breakerHalted : t.chrome.breakerArmed}
        </div>

        {/* Not a control: the environment is asserted at startup and again at every
            order. This states it; it does not select it. */}
        <div className="flex shrink-0 items-center gap-[7px] border-l border-line px-3 font-mono text-[11px] font-semibold leading-none text-amber">
          {t.chrome.paper}
        </div>

        {/* Armed or rehearsing. A dry run gates and journals exactly as a live one
            does and stops before submission, so its records are indistinguishable
            from a live run's — a REJECTED written by a rehearsal was read as the
            broker refusing an order, which is the failure this exists to prevent.
            Unknown is its own state and shows as neither. */}
        <div className={cn("flex shrink-0 items-center gap-[7px] border-l border-line px-3 font-mono text-[11px] font-semibold leading-none",
          armed === null ? "text-ink/30" : armed ? "text-pass" : "text-ink/45")}
             title={armed === null ? t.chrome.armedUnknownTitle
                    : armed ? t.chrome.armedTitle : t.chrome.dryRunTitle}>
          {armed === null ? t.chrome.armedUnknown
           : armed ? t.chrome.armed : t.chrome.dryRun}
        </div>

        {/* Whether it is mid-cycle, on every tab. Derived from the last record the
            agent wrote, so it goes quiet on its own if the process dies. */}
        {busy && (
          <div className="flex shrink-0 items-center gap-[7px] border-l border-line px-3 font-mono text-[11px] leading-none text-amber"
               title={t.chrome.busyTitle}>
            <span className={cn(CLS.dot, "animate-pulse bg-amber")} />
            <span>{busy.stage}</span>
            {busy.underlying && <span className="font-semibold">{busy.underlying}</span>}
          </div>
        )}

        <SessionBell />

        <div className="flex shrink-0 items-center gap-[7px] border-l border-line px-3 font-mono text-[11px] font-semibold leading-none tabular-nums text-ink">
          {t.chrome.equity} {snap ? money(snap.pnl.equity_last) : "—"}
        </div>

        <SoundToggle />
      </div>
    </div>
  );
}
