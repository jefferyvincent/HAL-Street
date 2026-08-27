import { create } from "zustand";
/**
 * What the operator is looking at. Deliberately the only mutable state in the app —
 * everything else is the server's snapshot, rendered.
 *
 * The selection is held as a timestamp rather than an object reference: a new push
 * replaces every decision object, so a reference would silently deselect on each
 * update, and an index would slide as records arrive.
 */

export type View = "console" | "journal" | "gates" | "committee" | "book";

interface UI {
  view: View;
  /** ts of the selected decision, or null to follow the newest. */
  selected: string | null;
  /** structure_id of the position being charted, or null for the list. */
  charting: string | null;
  setView: (v: View) => void;
  select: (ts: string | null) => void;
  /** Clicking a position charts it; the book view swaps its list for the chart. */
  chart: (structureId: string | null) => void;
  /** Audio cues off. Persisted, because a console that forgets is one you mute daily. */
  muted: boolean;
  setMuted: (muted: boolean) => void;
  /**
   * Whether the decision record is open.
   *
   * Collapsed by default: it is a rationale and sixteen verdicts, and it sits under
   * the run's numbers, the equity curve and the open book. What a reader wants from
   * it at a glance is the verdict, which stays in the header — the rest is there
   * when they go looking.
   */
  decisionOpen: boolean;
  toggleDecision: () => void;
  /**
   * What the structure chart's price axis is scaled to.
   *
   * `working` is the default: the price action plus every level close enough to sit
   * beside it, which is entry and target on every structure this agent builds. A
   * stop four times the candle range away is left out, because including it is not a
   * preference — it is geometry, and it flattens the candles into a fifth of the
   * height. `levels` pulls it in when that is what you want to see.
   */
  chartFit: "working" | "levels";
  toggleFit: () => void;
  /**
   * Select a decision *and* show it.
   *
   * `select` alone stopped being enough the moment the record became collapsible:
   * clicking a row in the run journal changed a selection nobody could see, so the
   * click read as broken. Choosing a thing and looking at it are one action here.
   */
  showDecision: (ts: string) => void;
}

/**
 * Muted by default, and remembered.
 *
 * Default-on would mean a page that makes noise the first time anyone opens it,
 * which is the wrong first impression for a risk console and is what browsers
 * refuse to allow anyway. Reading is wrapped because storage throws outright in a
 * private window and in a thumbnail capture, and a preference is never worth a
 * blank screen.
 */
const MUTE_KEY = "halstreet.muted";

function storedMute(): boolean {
  try {
    return window.localStorage.getItem(MUTE_KEY) !== "false";
  } catch {
    return true;
  }
}

export const useUI = create<UI>((set) => ({
  view: "console",
  selected: null,
  charting: null,
  // Switching views clears the chart: coming back to the book should land on the
  // list, not on whatever was open three views ago.
  setView: (view) => set({ view, charting: null }),
  select: (selected) => set({ selected }),
  chart: (charting) => set({ charting, view: "book" }),
  decisionOpen: false,
  chartFit: "working",
  toggleFit: () => set((s) => ({ chartFit: s.chartFit === "working" ? "levels" : "working" })),
  toggleDecision: () => set((s) => ({ decisionOpen: !s.decisionOpen })),
  showDecision: (selected) => set({ selected, decisionOpen: true, view: "console" }),
  muted: storedMute(),
  setMuted: (muted) => {
    try {
      window.localStorage.setItem(MUTE_KEY, String(muted));
    } catch {
      // Preference is per-browser and disposable; failing to save it is not a
      // reason to fail to apply it.
    }
    set({ muted });
  },
}));
