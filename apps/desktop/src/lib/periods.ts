/** The window the console opens on, and the one a fresh journal can actually measure. */
export const DEFAULT_PERIOD = "day";

/**
 * Which window to show, given what the server offers and what the reader last chose.
 *
 * The two can disagree. The choice outlives a reload and the server's list is built
 * per request, so a remembered key can arrive at a panel that no longer offers it —
 * and showing nothing because of that reads as a broken switcher rather than as a
 * changed menu.
 *
 * `null` only when there is genuinely nothing to show.
 */
export function chosenPeriod(available: string[], wanted: string | null): string | null {
  if (available.length === 0) return null;
  if (wanted && available.includes(wanted)) return wanted;
  if (available.includes(DEFAULT_PERIOD)) return DEFAULT_PERIOD;
  return available[0]!;
}
