/** SVG path data. Space-separated subpaths; `Icon` splits on " M". */

export const ICON = {
  hal: "M4 17l6-6-6-6 M12 19h8",
  grid: "M3 3h18v18H3z M3 9h18 M9 21V9",
  list: "M8 6h13M8 12h13M8 18h13 M3 6h.01 M3 12h.01 M3 18h.01",
  chain: "M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z",
  shield: "M4 10h16v10H4z M8 10V7a4 4 0 018 0v3",
  pulse: "M3 12h4l3 7 4-14 3 7h4",
  info: "M4 12a8 8 0 1 0 16 0 8 8 0 1 0-16 0 M12 11v6 M12 8h.01",
  // Three figures at a table: the catalyst, and the two who argue.
  committee: "M5 20v-2a3 3 0 013-3h1 M12 20v-3a3 3 0 013-3h1a3 3 0 013 3v3 M8.5 8a2 2 0 104 0 2 2 0 10-4 0 M15 5a2 2 0 104 0 2 2 0 10-4 0 M3 7a2 2 0 104 0 2 2 0 10-4 0",
  candles: "M6 4v3 M6 15v5 M4 7h4v8H4z M17 3v5 M17 17v4 M15 8h4v9h-4z",
  back: "M15 5l-7 7 7 7",
  chevron: "M6 9l6 6 6-6",
  // Direction, for a figure whose sign is the point. Solid triangles rather than
  // arrows: at ten pixels an arrowhead and its shaft blur into a smudge.
  up: "M12 6l7 12H5z",
  down: "M12 18L5 6h14z",
  tick: "M4 12l5 5L20 6",
  cross: "M6 6l12 12 M18 6L6 18",
  // The opening/closing bell. Struck, not a notification bell — flared skirt, clapper.
  bell: "M12 3a6 6 0 00-6 6c0 4-2 5-2 7h16c0-2-2-3-2-7a6 6 0 00-6-6z M10 19a2 2 0 004 0",
  // Speaker with waves; the muted variant strikes them through.
  sound: "M4 9v6h4l5 4V5L8 9H4z M16.5 8.5a5 5 0 010 7 M19 6a9 9 0 010 12",
  muted: "M4 9v6h4l5 4V5L8 9H4z M17 9l5 6 M22 9l-5 6",
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
