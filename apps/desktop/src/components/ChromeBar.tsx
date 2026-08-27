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
  const snap = useConnection((s) => s.snapshot);
  const halted = snap?.circuit.halted ?? false;

  return (
    <div className="sticky top-0 z-10 flex h-[34px] items-center border-b border-line bg-chrome">
      <div className="flex h-full shrink-0 items-center gap-[7px] bg-amber px-[14px]">
        <Icon d={ICON.hal} size={14} stroke={STROKE.void} width={2.2} />
        <span className="font-mono text-[12px] font-bold leading-none tracking-[.06em] text-void">
          {t.chrome.brand}
        </span>
      </div>

      {/* The tabs take whatever room is left and scroll inside it. Everything in
          this bar used to be one unbroken flex row with nothing pinned, so a narrow
          window squeezed the tab labels into each other instead of the bar admitting
          it had run out of space. Each item is now `shrink-0` and this strip is the
          only thing that gives. */}
      <div className="flex h-full min-w-0 flex-1 items-center overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => go(tab.id)}
            className={cn(CLS.tab, "shrink-0", tab.active ? CLS.tabOn : CLS.tabOff)}
          >
            <Icon d={tab.icon} stroke={tab.active ? STROKE.amber : "currentColor"} />
            {t.tabs[tab.id]}
            {tab.count !== null && <span className="tabular-nums">{tab.count}</span>}
          </button>
        ))}
      </div>

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

      {/* Whether it is mid-cycle, on every tab. Derived from the last record the
          agent wrote, so it goes quiet on its own if the process dies. */}
      {busy && (
        <div className="flex shrink-0 items-center gap-[7px] border-l border-line px-3 font-mono text-[11px] leading-none text-amber"
             title={t.chrome.busyTitle}>
          <span className={cn(CLS.dot, "animate-pulse bg-amber")} />
          <span className="hidden min-[1180px]:inline">{busy.stage}</span>
          {busy.underlying && <span className="font-semibold">{busy.underlying}</span>}
        </div>
      )}

      <SessionBell />

      <div className="flex shrink-0 items-center gap-[7px] border-l border-line px-3 font-mono text-[11px] font-semibold leading-none tabular-nums text-ink">
        {t.chrome.equity} {snap ? money(snap.pnl.equity_last) : "—"}
      </div>

      <SoundToggle />
    </div>
  );
}
