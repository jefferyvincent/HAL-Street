/**
 * What a structure is worth at expiry, across the underlying's whole range.
 *
 * The price chart beside this one answers "what has this position done"; this answers
 * "what can it do", which is the question the strikes were chosen to shape and the one
 * the net-price line cannot show at all. It is arithmetic over the legs — no model, no
 * quote, no broker call — so it is drawable the moment a position exists, including on
 * a day the chain will not load.
 *
 * Sign convention is the one the rest of the system uses: the structure's net price is
 * negative when it is held for a credit, and `contracts` is already signed and already
 * scaled by size. Both come straight off the chart payload rather than being
 * re-derived here, because two derivations of one number is how a picture starts
 * disagreeing with the ledger it claims to draw.
 */

/** The multiplier every listed equity option carries. */
const CONTRACT_SIZE = 100;

/** OCC: root, 6-digit date, C or P, then the strike in thousandths, 8 digits. */
const OCC = /^([A-Z]{1,6})(\d{2})(\d{2})(\d{2})([CP])(\d{8})$/;

export interface Contract {
  root: string;
  /** ISO, so it sorts and reads the same way every other date in the panel does. */
  expiry: string;
  right: "C" | "P";
  strike: number;
}

/** One leg as the chart payload already describes it: signed, and scaled by size. */
export interface PayoffLeg {
  symbol: string;
  contracts: number;
}

export interface PayoffPoint {
  s: number;
  pnl: number;
}

export interface PayoffCurve {
  points: PayoffPoint[];
  /** Where the curve crosses zero, ascending. Empty when it never does. */
  breakevens: number[];
  /** Null when the curve does not turn — an unbounded wing has no worst case. */
  maxGain: number | null;
  maxLoss: number | null;
  boundedAbove: boolean;
  boundedBelow: boolean;
  strikes: number[];
  lo: number;
  hi: number;
}

/**
 * The contract a symbol names, or null if it does not name one.
 *
 * Null rather than a guess. A leg whose strike cannot be read cannot be placed on the
 * x-axis, and defaulting it to zero would draw a cliff at the origin that looks like
 * a real risk.
 */
export function parseOcc(symbol: string): Contract | null {
  const m = OCC.exec(symbol.trim().toUpperCase());
  if (!m) return null;
  // Asserted rather than checked: the regex matched, so every group is present.
  return {
    root: m[1]!,
    expiry: `20${m[2]!}-${m[3]!}-${m[4]!}`,
    right: m[5] as "C" | "P",
    strike: Number(m[6]!) / 1000,
  };
}

/** What one contract is worth at expiry with the underlying at `s`. */
function intrinsic(contract: Contract, s: number): number {
  return contract.right === "C"
    ? Math.max(s - contract.strike, 0)
    : Math.max(contract.strike - s, 0);
}

/**
 * The structure's P&L in dollars if the underlying finishes at `s`.
 *
 * `entry` is the net price per structure on the credit-is-negative convention, so it
 * is multiplied by size here while the legs are not — they carry size already.
 */
export function payoff(legs: PayoffLeg[], entry: number, qty: number, s: number): number {
  let value = 0;
  for (const leg of legs) {
    const contract = parseOcc(leg.symbol);
    if (!contract) continue;
    value += leg.contracts * intrinsic(contract, s);
  }
  return CONTRACT_SIZE * (value - entry * qty);
}

/**
 * The slope of the curve beyond the outermost strike, in contracts.
 *
 * Zero means the wing is flat and the structure is bounded that side. Anything else
 * is an open end, and an open end has no max — see `payoffCurve`.
 */
function wingSlope(contracts: Contract[], legs: PayoffLeg[], side: "above" | "below"): number {
  let slope = 0;
  legs.forEach((leg, i) => {
    const contract = contracts[i];
    if (!contract) return;
    if (side === "above" && contract.right === "C") slope += leg.contracts;
    if (side === "below" && contract.right === "P") slope -= leg.contracts;
  });
  return slope;
}

/**
 * Everything the payoff chart draws, or null if it cannot honestly draw anything.
 *
 * Sampled at the strikes and the two ends and nowhere else, because the function is
 * piecewise linear with a kink at every strike and straight between them: more points
 * would be more arithmetic for an identical picture, and fewer would round a corner
 * the trade was built around.
 */
export function payoffCurve(legs: PayoffLeg[], entry: number | null, qty: number,
                            spot: number | null): PayoffCurve | null {
  if (entry === null || !legs.length) return null;

  const contracts = legs.map((leg) => parseOcc(leg.symbol));
  if (contracts.some((c) => c === null)) return null;
  const known = contracts as Contract[];

  const strikes = [...new Set(known.map((c) => c.strike))].sort((a, b) => a - b);
  const low = strikes[0]!;
  const high = strikes[strikes.length - 1]!;

  // Enough air to show the wings flattening. The widest gap between strikes is the
  // structure's own scale, so a $10 condor gets $10 of margin and a $200 one does not
  // get the same $10 and look vertical.
  const widest = strikes.length > 1
    ? Math.max(...strikes.slice(1).map((s, i) => s - strikes[i]!))
    : high * 0.05;
  const pad = Math.max(widest, high * 0.03);
  const lo = Math.max(0, Math.min(low - pad, spot ?? Infinity));
  const hi = Math.max(high + pad, spot ?? 0);

  const at = (s: number) => ({ s, pnl: payoff(legs, entry, qty, s) });
  const points = [at(lo), ...strikes.map(at), at(hi)];

  const breakevens: number[] = [];
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1]!;
    const b = points[i]!;
    if (a.pnl === 0) breakevens.push(a.s);
    else if ((a.pnl < 0) !== (b.pnl < 0)) {
      // Linear between two kinks, so the crossing is exact rather than searched for.
      breakevens.push(a.s + ((0 - a.pnl) / (b.pnl - a.pnl)) * (b.s - a.s));
    }
  }
  if (points[points.length - 1]!.pnl === 0) breakevens.push(hi);

  const boundedAbove = wingSlope(known, legs, "above") === 0;
  const boundedBelow = wingSlope(known, legs, "below") === 0;
  const values = points.map((p) => p.pnl);
  const highest = Math.max(...values);
  const lowest = Math.min(...values);

  // A wing that keeps going has no extreme to report on the side it runs away in, and
  // the worst point on a range this module chose is not a risk figure. Which side an
  // open end costs depends on its direction: an unbounded wing that rises has no max
  // gain, one that falls has no max loss.
  const openUp = (!boundedAbove && wingSlope(known, legs, "above") > 0)
    || (!boundedBelow && wingSlope(known, legs, "below") > 0);
  const openDown = (!boundedAbove && wingSlope(known, legs, "above") < 0)
    || (!boundedBelow && wingSlope(known, legs, "below") < 0);

  return {
    points,
    breakevens: [...new Set(breakevens)].sort((a, b) => a - b),
    maxGain: openUp ? null : highest,
    maxLoss: openDown ? null : lowest,
    boundedAbove,
    boundedBelow,
    strikes,
    lo,
    hi,
  };
}
