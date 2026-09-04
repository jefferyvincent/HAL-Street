import type { ChainEntry, Decision, GateVerdict } from "@/types";

/**
 * Grouping verdicts by family — never by position.
 *
 * The gate layer stamps each verdict with the module it came from. Slicing the chain
 * positionally instead (the first two are contract, the next two liquidity…) breaks
 * the moment a gate is inserted: every gate after it is relabelled, and the panel
 * shows the wrong family with complete confidence. This is the whole reason `family`
 * travels on the verdict.
 */

/**
 * Records journalled before verdicts carried a family still resolve, by looking the
 * gate up in the chain the server serves. Older history stays grouped correctly
 * instead of collapsing into one "other" bucket.
 */
export const familyOf = (g: GateVerdict, chain: ChainEntry[]): string =>
  g.family || chain.find((c) => c.gate === g.gate)?.family || "other";

export function byFamily(
  gates: GateVerdict[],
  families: string[],
  chain: ChainEntry[],
): [string, GateVerdict[]][] {
  const stamped = gates.map((g) => ({ ...g, family: familyOf(g, chain) }));
  const seen = [...new Set(stamped.map((g) => g.family))];
  // Server order first, so the meter reads the way the chain evaluates; anything the
  // server did not name goes after, rather than being dropped.
  const order = families.filter((f) => seen.includes(f)).concat(seen.filter((f) => !families.includes(f)));
  return order.map((f) => [f, stamped.filter((g) => g.family === f)]);
}

export const failed = (d: Decision | null): GateVerdict[] =>
  (d?.gates ?? []).filter((g) => !g.passed);
