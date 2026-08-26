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
    gates: snap?.chain.length ?? null,
    book: snap ? snap.positions.length + snap.closed.length : null,
  };

  const tabs: Tab[] = (
    [
      ["console", "CONSOLE", ICON.grid],
      ["journal", "JOURNAL", ICON.list],
      ["gates", "GATES", ICON.chain],
      ["book", "BOOK", ICON.candles],
    ] as [View, string, string][]
  ).map(([id, , icon]) => ({ id, icon, count: counts[id], active: id === view }));

  return { tabs, go };
}
