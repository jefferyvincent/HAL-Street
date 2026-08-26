import { useMemo } from "react";
import { neighbours, newestFirst, resolve, type Row } from "@/lib/decisions";
import { useConnection } from "@/stores/connection";
import { useUI } from "@/stores/ui";
import type { Decision } from "@/types";

export interface Decisions {
  all: Decision[];
  /** Newest first, already counted — what both the table and the tape render. */
  rows: Row[];
  /** The decision on screen: the selected one, or the newest when nothing is pinned. */
  current: Decision | null;
  selected: string | null;
  prev: string | null;
  next: string | null;
}

/**
 * The journal, resolved against the current selection.
 *
 * Every view that shows decisions goes through here, so "which one is on screen" is
 * answered in one place rather than three slightly different ways.
 */
export function useDecisions(): Decisions {
  const all = useConnection((s) => s.snapshot?.decisions) ?? [];
  const selected = useUI((s) => s.selected);

  return useMemo(() => {
    const current = resolve(all, selected);
    return { all, rows: newestFirst(all), current, selected, ...neighbours(all, current) };
  }, [all, selected]);
}
