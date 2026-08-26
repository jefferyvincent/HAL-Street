/**
 * Values that are not markup and not copy: the palette as the chart needs it, the
 * layout breakpoints, and the class strings that repeat.
 *
 * The palette is defined once in `styles/globals.css` as Tailwind theme tokens. These
 * literals exist because lightweight-charts takes colours as strings through a
 * JavaScript API and cannot read a CSS variable — so they are a mirror, and the
 * comment beside each one names the token it must match.
 */

export const CHART_COLOR = {
  line: "#e8a33d", // --color-amber
  fillTop: "rgba(232,163,61,.22)",
  fillBottom: "rgba(232,163,61,0)",
  grid: "#1f252a", // --color-line-soft
  border: "#23292e", // --color-line
  text: "rgba(233,237,240,.4)", // --color-ink at 40%
  crosshair: "#e8a33d", // --color-amber
} as const;

export const STROKE = {
  pass: "#21d07a", // --color-pass
  fail: "#ff4d4f", // --color-fail
  amber: "#e8a33d", // --color-amber
  agent: "#4fc3f7", // --color-agent
  void: "#0b0d0e", // --color-void
  ink: "#e9edf0", // --color-ink
  muted: "rgba(233,237,240,.4)",
  faint: "rgba(233,237,240,.35)",
} as const;

/** Column layouts. The wide views drop the rails rather than shrink them. */
export const GRID = {
  console: "grid flex-1 grid-cols-1 min-[1181px]:grid-cols-[200px_minmax(0,1fr)_320px]",
  wide: "grid flex-1 grid-cols-1",
  decision: "grid grid-cols-1 min-[901px]:grid-cols-[minmax(0,1fr)_316px]",
} as const;

/** Class strings used in more than one place, so they stay one thing. */
export const CLS = {
  tab: "flex h-full cursor-pointer items-center gap-[6px] border-r border-line px-[13px] font-mono text-[11px] leading-none",
  tabOn: "bg-panel font-semibold text-ink",
  tabOff: "font-normal text-ink/40 hover:bg-panel",
  note: "flex gap-[9px] border border-line bg-void px-3 py-[10px] font-sans text-[11.5px] leading-[1.5] text-ink/40",
  caption: "mt-[11px] mb-[5px] font-mono text-[8.5px] font-bold leading-none tracking-[.12em]",
  heading: "mb-3 flex items-baseline gap-[9px] border-b border-line pb-2 font-mono text-[11px] font-bold leading-none tracking-[.12em] text-ink",
  headingMeta: "font-mono text-[10px] font-normal leading-none tracking-[.06em] text-ink/40",
  th: "whitespace-nowrap border-b border-line bg-sunk px-3 py-[7px] text-left font-mono text-[9px] font-bold leading-none tracking-[.12em] text-ink/40",
  td: "border-b border-line-soft px-3 py-[9px] align-top font-mono text-[11px] leading-[1.4] text-ink/60",
  key: "px-[11px] font-mono text-[10px] font-semibold leading-none text-ink/40",
  empty: "p-4 font-sans text-[13px] leading-[1.5] text-ink/40",
  dot: "h-[6px] w-[6px] rounded-full",
} as const;
