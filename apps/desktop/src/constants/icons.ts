/** SVG path data. Space-separated subpaths; `Icon` splits on " M". */

export const ICON = {
  hal: "M4 17l6-6-6-6 M12 19h8",
  grid: "M3 3h18v18H3z M3 9h18 M9 21V9",
  list: "M8 6h13M8 12h13M8 18h13 M3 6h.01 M3 12h.01 M3 18h.01",
  chain: "M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z",
  shield: "M4 10h16v10H4z M8 10V7a4 4 0 018 0v3",
  pulse: "M3 12h4l3 7 4-14 3 7h4",
  info: "M4 12a8 8 0 1 0 16 0 8 8 0 1 0-16 0 M12 11v6 M12 8h.01",
  candles: "M6 4v3 M6 15v5 M4 7h4v8H4z M17 3v5 M17 17v4 M15 8h4v9h-4z",
  back: "M15 5l-7 7 7 7",
  tick: "M4 12l5 5L20 6",
  cross: "M6 6l12 12 M18 6L6 18",
} as const;

/** One glyph per gate family, keyed by the family the server stamps. */
export const FAMILY_ICON: Record<string, string> = {
  contract: "M6 3h9l4 4v14H6z M9 12h7M9 16h5",
  liquidity: "M3 17l5-6 4 3 4-7 5 4",
  defined_risk: "M4 16l4-8 4 5 4-9 4 12",
  portfolio: "M4 12a8 8 0 1 0 16 0 8 8 0 1 0-16 0 M12 12l5-3",
  circuit: "M13 2L4 14h6l-1 8 9-12h-6z",
  other: "M4 12a8 8 0 1 0 16 0 8 8 0 1 0-16 0",
};
