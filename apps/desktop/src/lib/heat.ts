/**
 * The heat map's arithmetic: how loud the tape was about a name, and what came of it.
 *
 * Two channels, and keeping them independent is the whole design. Heat is mention
 * count — a fact about the feed. Status is what the agent did — scanned it, refused
 * it, or never got to it. Smearing the two together would make the map assert things
 * nobody established: a name below the cut is not a *cold* name, it is an unexamined
 * one, and a refused name was often among the loudest on the page.
 *
 * No words here, by rule. This file returns numbers and CSS; every label the map
 * carries comes through `useStrings`.
 */

/** The palest a mentioned name may be drawn. */
export const COLD_FLOOR = 0.18;

/** What the map knows how to draw. Anything else falls back to the unexamined tone. */
export type CellStatus = "scanned" | "refused" | "not-reached";

export interface RawCell {
  symbol: string;
  mentions: number;
  status: string;
  headline: string;
  reason?: string;
}

export interface HeatCell {
  symbol: string;
  mentions: number;
  headline: string;
  status: string;
  /** Why the screen refused it, or null when there was no objection. */
  reason: string | null;
  /** 0..1 against the loudest name in this census. */
  level: number;
}

/**
 * Where one name sits on the ramp, relative to the loudest in the same census.
 *
 * Relative rather than absolute because both are true and only one is useful: a
 * four-mention morning drawn on a forty-mention scale is a uniformly cold grid, and
 * the reader learns nothing about which of those four names the tape cared about.
 *
 * Floored rather than starting at zero. The tail is why this is a map instead of a
 * list, and a cell at zero opacity is a cell that is not there.
 */
export function heatLevel(mentions: number, hottest: number): number {
  if (!Number.isFinite(mentions) || mentions <= 0) return COLD_FLOOR;
  const scale = Number.isFinite(hottest) && hottest > 0 ? hottest : 1;
  const share = Math.min(mentions / scale, 1);
  return COLD_FLOOR + share * (1 - COLD_FLOOR);
}

/**
 * The census as cells, loudest first.
 *
 * Ties break on symbol so the grid does not reshuffle between polls. The map repaints
 * every five seconds and a tile that moves on equal counts is one nobody can point at.
 */
export function heatCells(cells: RawCell[], hottest: number): HeatCell[] {
  return cells
    .map((c) => ({
      symbol: c.symbol,
      mentions: c.mentions,
      headline: c.headline,
      status: c.status,
      reason: c.reason || null,
      level: heatLevel(c.mentions, hottest),
    }))
    .sort((a, b) => b.mentions - a.mentions || a.symbol.localeCompare(b.symbol));
}

/**
 * One tile's colours: heat in the fill, outcome in the border and the text.
 *
 * Amber is the chrome's own hue and the agent's colour throughout the panel, so a hot
 * name reads as "this is what it is looking at" without a legend. The outcome rides on
 * the border because it is a boundary property — a name was let through or it was not
 * — and on the text because a struck-out symbol has to stay legible enough to read.
 */
export function heatStyle(level: number, status: string) {
  const fill = `hsl(38 90% 55% / ${(level * 0.42).toFixed(3)})`;
  if (status === "refused") {
    return {
      backgroundColor: fill,
      borderColor: "hsl(4 70% 52% / 0.5)",
      color: "hsl(4 60% 72%)",
    };
  }
  if (status === "scanned") {
    return {
      backgroundColor: fill,
      borderColor: `hsl(38 80% 55% / ${(0.25 + level * 0.5).toFixed(3)})`,
      color: "hsl(38 75% 78%)",
    };
  }
  // Never screened. Drawn at its real heat — that is what the tape said — with no
  // verdict colour at all, because none was reached.
  return {
    backgroundColor: fill,
    borderColor: "hsl(210 12% 40% / 0.35)",
    color: "hsl(210 14% 62%)",
  };
}
