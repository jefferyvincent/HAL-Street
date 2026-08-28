import { useMemo } from "react";

import { KEY, VIEW_KEYS } from "@/constants/keys";
import { useStrings } from "@/hooks/useStrings";

export interface Shortcut {
  /** The keys as they are printed. Several only where one label covers them all. */
  keys: string[];
  label: string;
}

/**
 * The keys the footer advertises — the ones `useShortcuts` actually binds.
 *
 * Both read `constants/keys.ts`, so the footer cannot go on offering a key that no
 * longer does anything. Nothing here writes: there is no PROPOSE and no HALT because
 * the panel can do neither, and an advertised key that does nothing is the same lie
 * as a dead tab.
 */
export function useShortcutLegend(): Shortcut[] {
  const t = useStrings();

  return useMemo(() => [
    { keys: [KEY.prev.toUpperCase()], label: t.status.prev },
    { keys: [KEY.next.toUpperCase()], label: t.status.next },
    { keys: [KEY.latest.toUpperCase()], label: t.status.latest },
    { keys: Object.keys(VIEW_KEYS), label: t.status.view },
  ], [t]);
}
