import { cn } from "@/lib/cn";
import { money } from "@/lib/format";
import { ICON } from "@/constants/icons";
import { CLS, STROKE } from "@/constants/theme";
import { useStrings } from "@/hooks/useStrings";
import { useTabs } from "@/hooks/useTabs";
import { useConnection } from "@/stores/connection";
import { Icon } from "./Icon";

export function ChromeBar() {
  const t = useStrings();
  const { tabs, go } = useTabs();
  const snap = useConnection((s) => s.snapshot);
  const halted = snap?.circuit.halted ?? false;

  return (
    <div className="sticky top-0 z-10 flex h-[34px] items-center border-b border-line bg-chrome">
      <div className="flex h-full items-center gap-[7px] bg-amber px-[14px]">
        <Icon d={ICON.hal} size={14} stroke={STROKE.void} width={2.2} />
        <span className="font-mono text-[12px] font-bold leading-none tracking-[.06em] text-void">
          {t.chrome.brand}
        </span>
      </div>

      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => go(tab.id)}
          className={cn(CLS.tab, tab.active ? CLS.tabOn : CLS.tabOff)}
        >
          <Icon d={tab.icon} stroke={tab.active ? STROKE.amber : "currentColor"} />
          {t.tabs[tab.id]}
          {tab.count !== null && <span className="tabular-nums">{tab.count}</span>}
        </button>
      ))}

      <div className="flex-1" />

      <div className={cn("flex items-center gap-[7px] px-3 font-mono text-[11px] font-semibold leading-none",
        halted ? "text-fail" : "text-pass")}>
        <span className={cn(CLS.dot, halted ? "bg-fail" : "bg-pass")} />
        {halted ? t.chrome.breakerHalted : t.chrome.breakerArmed}
      </div>

      {/* Not a control: the environment is asserted at startup and again at every
          order. This states it; it does not select it. */}
      <div className="flex items-center gap-[7px] border-l border-line px-3 font-mono text-[11px] font-semibold leading-none text-amber">
        {t.chrome.paper}
      </div>

      <div className="flex items-center gap-[7px] border-l border-line px-3 font-mono text-[11px] font-semibold leading-none tabular-nums text-ink">
        {t.chrome.equity} {snap ? money(snap.pnl.equity_last) : "—"}
      </div>
    </div>
  );
}
