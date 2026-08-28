/**
 * Which way a figure went, or nothing at all.
 *
 * Nothing for zero, and nothing for a figure that could not be parsed. A scratch is
 * neither direction, and an arrow pointing somewhere would be asserting a direction
 * the number does not have.
 *
 * Values arrive as decimal strings from the ledger and as numbers from the panel's
 * own arithmetic, so the coercion lives here rather than in every caller.
 */
export function useTrend(value: number | string | null): "up" | "down" | null {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return null;
  return n > 0 ? "up" : "down";
}
