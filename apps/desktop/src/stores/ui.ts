import { create } from "zustand";
/**
 * What the operator is looking at. Deliberately the only mutable state in the app —
 * everything else is the server's snapshot, rendered.
 *
 * The selection is held as a timestamp rather than an object reference: a new push
 * replaces every decision object, so a reference would silently deselect on each
 * update, and an index would slide as records arrive.
 */

export type View = "console" | "agent" | "journal" | "discovery" | "gates"
  | "committee" | "book";

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
  /**
   * Whether the committee tab shows the sessions behind the desk.
   *
   * Closed by default, and that is the point rather than tidiness: the tab used
   * to open on a stack of finished cards, so most of the screen was deliberations
   * from five and eighteen hours ago while the desk was one word in a header.
   * They are still there, one control away, and the control says how many.
   */
  archiveOpen: boolean;
  toggleDecision: () => void;
  toggleArchive: () => void;
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
   * Bar size for the structure chart, or null to let the window decide.
   *
   * Held here rather than in the chart so it survives closing one and opening
   * another — someone who wanted five-minute bars wants them for the next position
   * too, and re-picking it every time is the kind of small friction that makes a
   * control not worth having.
   */
  chartTimeframe: string | null;
  setTimeframe: (timeframe: string | null) => void;
  /**
   * Which P&L window the console shows, or null before anyone has chosen.
   *
   * Here rather than in the view so it survives switching tabs and coming back — a
   * trader who set the console to MONTH did not mean "until I look at the book".
   * Which window is actually shown is `lib/periods.chosenPeriod`, because a stored
   * key can outlive the server's offer of it.
   */
  pnlPeriod: string | null;
  setPnlPeriod: (period: string) => void;
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
 * Sound on by default, and remembered.
 *
 * This was muted by default, on the argument that a page should not make noise the
 * first time anyone opens it. The argument was wrong for this page: the bells are
 * the only thing that tells you the market turned while you were looking elsewhere,
 * and a default that has to be found before it works is a feature nobody hears.
 *
 * The browser constraint behind the old default is real and does not go away —
 * an AudioContext created outside a user gesture starts suspended and stays that
 * way, so *wanting* sound and *being able to make it* are two different states. The
 * preference now defaults to on and `useAudioUnlock` arms the context on the first
 * click, key or touch anywhere in the page. Until that happens the panel is silent
 * and the toggle says so.
 *
 * Reading is wrapped because storage throws outright in a private window and in a
 * thumbnail capture, and a preference is never worth a blank screen.
 */
const MUTE_KEY = "halstreet.muted";

function storedMute(): boolean {
  try {
    // Only an explicit "true" mutes. An absent key is a first visit, and a first
    // visit should hear the bell.
    return window.localStorage.getItem(MUTE_KEY) === "true";
  } catch {
    return false;
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
  archiveOpen: false,
  chartFit: "working",
  chartTimeframe: null,
  setTimeframe: (chartTimeframe) => set({ chartTimeframe }),
  pnlPeriod: null,
  setPnlPeriod: (pnlPeriod) => set({ pnlPeriod }),
  toggleFit: () => set((s) => ({ chartFit: s.chartFit === "working" ? "levels" : "working" })),
  toggleDecision: () => set((s) => ({ decisionOpen: !s.decisionOpen })),
  toggleArchive: () => set((s) => ({ archiveOpen: !s.archiveOpen })),
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
