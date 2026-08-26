import { cn } from "@/lib/cn";
import { clock } from "@/lib/format";
import { CLS } from "@/constants/theme";
import type { FamilyGroup } from "@/hooks/useGateFamilies";
import { useStatus } from "@/hooks/useStatus";
import { useStrings } from "@/hooks/useStrings";

/**
 * The footer advertises only shortcuts that are bound.
 *
 * The mockup drew a row of F-keys, several of which were writes — F1 PROPOSE, F8 HALT
 * LATCH. This panel can do neither, so drawing them would be the same lie as a tab
 * with nothing behind it. What is here walks the journal and switches views, which is
 * all a read-only surface has to offer.
 */
export function StatusBar({ families }: { families: FamilyGroup[] }) {
  const t = useStrings();
  const { connected, transport, error, at, gates, meter } = useStatus(families);

  const Key = ({ k, label }: { k: string; label: string }) => (
    <span className={CLS.key}><b className="font-bold text-amber">{k}</b> {label}</span>
  );

  return (
    <div className="sticky bottom-0 flex h-[28px] items-center border-t border-line bg-chrome">
      <Key k="J" label={t.status.prev} />
      <Key k="K" label={t.status.next} />
      <Key k="L" label={t.status.latest} />
      <span className={CLS.key}>
        <b className="font-bold text-amber">1</b>·<b className="font-bold text-amber">2</b>·
        <b className="font-bold text-amber">3</b>·
        <b className="font-bold text-amber">4</b> {t.status.view}
      </span>
      <span className={cn(CLS.key, "hidden min-[901px]:inline")}>{meter}</span>

      <div className="flex-1" />

      <span className={CLS.key}>
        {t.status.updated} <span className="tabular-nums">{clock(at) || "—"}</span>
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
