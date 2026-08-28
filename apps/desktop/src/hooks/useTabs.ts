import { useConnection } from "@/stores/connection";
import { useUI, type View } from "@/stores/ui";
import { ICON } from "@/constants/icons";

export interface Tab {
  id: View;
  icon: string;
  /** Rendered beside the label; null when the tab has nothing to count. */
  count: number | null;
  active: boolean;
}

/** The chrome bar's tabs, each one carrying its own live count. */
export function useTabs(): { tabs: Tab[]; go: (v: View) => void } {
  const snap = useConnection((s) => s.snapshot);
  const view = useUI((s) => s.view);
  const go = useUI((s) => s.setView);

  const counts: Record<View, number | null> = {
    console: null,
    journal: snap?.decisions.length ?? null,
    // The census size, not the shortlist: the tab counts what the map draws.
    // Optional through `discovery` as well as `snap`: during a restart the panel can
    // be the new build talking to a server that has not reloaded yet, and a missing
    // key there would take the whole tab bar down rather than one count.
    discovery: snap?.discovery?.cells.length ?? null,
    gates: snap?.chain.length ?? null,
    committee: snap?.committees.length ?? null,
    book: snap ? snap.positions.length + snap.closed.length : null,
  };

  // Order and icon only. The words come from the string table, which is why there
  // is no label here to fall out of step with it.
  const tabs: Tab[] = (
    [
      ["console", ICON.grid],
      ["journal", ICON.list],
      ["discovery", ICON.heat],
      ["gates", ICON.chain],
      ["committee", ICON.committee],
      ["book", ICON.candles],
    ] as [View, string][]
  ).map(([id, icon]) => ({ id, icon, count: counts[id], active: id === view }));

  return { tabs, go };
}
