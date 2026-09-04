/**
 * Which symbols one ticker item is labelled with.
 *
 * Two sources feed the strip and they know different things about an article. A
 * committee read knows which of *our* underlyings pulled it up, which is a fact about
 * the desk. A census sighting knows only what the publisher tagged, which is a fact
 * about the article. The first is better when it exists, and it usually does not —
 * most of the strip is now census.
 *
 * The asymmetry in the cap is deliberate. Reads are our own scanned names and there
 * are only ever a few, so truncating them would hide that a third underlying also read
 * the story. Publisher tags run to a dozen on a market roundup, and a dozen chips on
 * one item is a wall the reader scrolls past — it crowds out the three stories behind
 * it, which is the opposite of what widening the source was for.
 */

/** Publisher tags drawn on one item at most. */
export const MAX_CHIPS = 3;

export function newsChips(roots?: string[], symbols?: string[]): string[] {
  if (roots?.length) return roots;
  const clean = (symbols ?? []).map((s) => s.trim()).filter(Boolean);
  return [...new Set(clean)].slice(0, MAX_CHIPS);
}
