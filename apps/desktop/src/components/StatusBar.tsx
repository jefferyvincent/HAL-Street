import { Fragment } from "react";

import { cn } from "@/lib/cn";
import { CLS } from "@/constants/theme";
import type { FamilyGroup } from "@/hooks/useGateFamilies";
import { useFormat } from "@/hooks/useFormat";
import { useShortcutLegend } from "@/hooks/useShortcutLegend";
import { useStatus } from "@/hooks/useStatus";
import { useStrings } from "@/hooks/useStrings";

/**
 * The footer advertises only shortcuts that are bound.
 *
 * The mockup drew a row of F-keys, several of which were writes — F1 PROPOSE, F8 HALT
 * LATCH. This panel can do neither, so drawing them would be the same lie as a tab
 * with nothing behind it. What is here walks the journal and switches views, which is
 * all a read-only surface has to offer — and it is the same list `useShortcuts` binds
 * rather than a copy of it.
 */
export function StatusBar({ families }: { families: FamilyGroup[] }) {
  const t = useStrings();
  const f = useFormat();
  const legend = useShortcutLegend();
  const { connected, transport, error, at, gates, meter } = useStatus(families);

  return (
    <div className="sticky bottom-0 flex h-[28px] items-center border-t border-line bg-chrome">
      {legend.map((shortcut) => (
        <span key={shortcut.label} className={CLS.key}>
          {shortcut.keys.map((k, i) => (
            <Fragment key={k}>
              {i > 0 && t.common.keySep}
              <b className="font-bold text-amber">{k}</b>
            </Fragment>
          ))}{" "}
          {shortcut.label}
        </span>
      ))}
      <span className={cn(CLS.key, "hidden min-[901px]:inline")}>{meter}</span>

      <div className="flex-1" />

      <span className={CLS.key}>
        {t.status.updated}{" "}
        <span className="tabular-nums">{f.clock(at) || t.common.dash}</span>
      </span>
      <span className={cn("flex items-center gap-[6px] px-3 font-mono text-[10px] font-semibold leading-none",
        connected ? "text-pass" : "text-fail")}>
        <span className={cn(CLS.dot, connected ? "bg-pass" : "bg-fail")} />
        {connected
          ? transport === "socket" ? t.status.live(gates) : t.status.polling(gates)
          : t.status.disconnected(error)}
      </span>
    </div>
  );
}
