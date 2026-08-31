/**
 * Whether a leg has a fill price, is still waiting for one, or lost one.
 *
 * Three different silences wearing the same words. The panel showed `not recorded`
 * against both legs of an order that had not filled — which reads as "it filled and we
 * failed to write it down", the one case here that would be a real defect. Nothing had
 * filled; the order was resting at its limit.
 *
 * This is the panel's rule six on the row where the money is: a reading that could not
 * be taken must not render the same as a reading that was lost.
 *
 * No words here, by rule. The caller spells it.
 */

/**
 * `known` a price we hold · `awaiting` the order has not filled · `missing` it filled
 * and the price was never recorded · `unknown` we do not yet know which.
 */
export type BasisState = "known" | "awaiting" | "missing" | "unknown";

/**
 * @param basis the recorded fill price, or null
 * @param filled whether the entry order has filled; null before the panel knows
 *
 * A recorded price wins over the flag. A partial fill records what filled, and the
 * number is real whatever the flag says — showing words over a price we hold would be
 * the panel hiding evidence it has.
 */
export function basisState(basis: string | null, filled: boolean | null): BasisState {
  if (basis !== null) return "known";
  if (filled === null) return "unknown";
  return filled ? "missing" : "awaiting";
}
