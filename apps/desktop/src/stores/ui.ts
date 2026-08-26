import { create } from "zustand";
/**
 * What the operator is looking at. Deliberately the only mutable state in the app —
 * everything else is the server's snapshot, rendered.
 *
 * The selection is held as a timestamp rather than an object reference: a new push
 * replaces every decision object, so a reference would silently deselect on each
 * update, and an index would slide as records arrive.
 */

export type View = "console" | "journal" | "gates" | "book";

interface UI {
  view: View;
  /** ts of the selected decision, or null to follow the newest. */
  selected: string | null;
  /** structure_id of the position being charted, or null for the list. */
  charting: string | null;
  setView: (v: View) => void;
  select: (ts: string | null) => void;
  /** Selecting from the journal table opens the decision record, which is the console. */
  open: (ts: string) => void;
  /** Clicking a position charts it; the book view swaps its list for the chart. */
  chart: (structureId: string | null) => void;
}

export const useUI = create<UI>((set) => ({
  view: "console",
  selected: null,
  charting: null,
  // Switching views clears the chart: coming back to the book should land on the
  // list, not on whatever was open three views ago.
  setView: (view) => set({ view, charting: null }),
  select: (selected) => set({ selected }),
  open: (selected) => set({ selected, view: "console" }),
  chart: (charting) => set({ charting, view: "book" }),
}));
