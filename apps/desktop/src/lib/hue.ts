/**
 * A stable hue per symbol.
 *
 * Deliberately not random and not sequential: the same ticker must get the same
 * colour on every machine and in every session, or the chip stops being a
 * recognisable shape and becomes decoration.
 */
export function hueOf(symbol: string): number {
  let hash = 0;
  for (const char of symbol) hash = (hash * 31 + char.charCodeAt(0)) % 360;
  // Nudged off the amber the chrome already uses, so a chip never reads as chrome.
  return (hash + 25) % 360;
}

/** The three colours a chip is drawn in, at one fixed saturation and lightness. */
export function chipColors(hue: number) {
  return {
    color: `hsl(${hue} 70% 68%)`,
    borderColor: `hsl(${hue} 55% 40% / 0.55)`,
    backgroundColor: `hsl(${hue} 60% 30% / 0.22)`,
  };
}
