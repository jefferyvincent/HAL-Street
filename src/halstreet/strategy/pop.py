"""Probability of profit, at expiry, for the structures this agent builds.

Ported from TradeScans' `pop-calculator.ts`, trimmed to the three structures HAL
Street actually constructs. The vendor file covered ten — straddles, calendars,
diagonals, covered calls — and porting probability functions for structures the
4-leg ceiling and the defined-risk gate will never let through would be dead code
pretending to be capability.

Every number here is **probability of profit at expiry**, which is not the same as
the probability of ever being profitable. A credit spread that can be closed at 50%
of max profit — which is exactly what the position manager does — reaches its target
more often than it expires in the money, so these figures are conservative for the
way the book is actually run. Conservative in the safe direction, and stated rather
than quietly assumed.

Breakevens, not short strikes, are what get tested. The credit received moves the
breakeven past the strike you sold, and using the strike instead would understate
every credit structure's odds by the width of its own premium.

**The credit is taken on trust, and cannot be checked here.** None of these functions
receives the wing width, so none of them can tell a real premium from a crossed quote:
a 99-point credit on a 2-point wing simply widens the profit zone by 99 and returns a
serene 95%, which would put the structure straight to the top of the ranking. The
invariant that stops that — `max_loss = (width - credit) * 100` must be positive, since
a spread that cannot lose is a bad quote rather than an opportunity — belongs to
`candidates.py`, which is the only layer that knows both numbers. It is enforced there
and pinned by `test_every_structure_built_can_actually_lose_something`; a credit
arriving here has already passed it. What *can* be checked here is checked below.

One improvement over the TypeScript: **each tail is priced with its own leg's IV.**
TradeScans passed a single volatility into the two-sided iron-condor calculation,
which ignores skew — and index put skew is steep enough that the downside tail is
materially fatter than a shared IV implies. Here the put side uses the short put's
IV and the call side the short call's, so the number reflects the surface we were
actually quoted.
"""

from __future__ import annotations

from halstreet.strategy.blackscholes import prob_above, prob_below


def credit_put_spread(spot: float, short_strike: float, credit: float,
                      dte: int, vol: float) -> float | None:
    """Bull put spread: wins as long as the underlying stays above the breakeven."""
    if credit < 0:
        return None
    return prob_above(spot, short_strike - credit, dte, vol)


def credit_call_spread(spot: float, short_strike: float, credit: float,
                       dte: int, vol: float) -> float | None:
    """Bear call spread: wins as long as the underlying stays below the breakeven."""
    if credit < 0:
        return None
    return prob_below(spot, short_strike + credit, dte, vol)


def iron_condor(spot: float, short_put: float, short_call: float, credit: float,
                dte: int, put_vol: float, call_vol: float | None = None) -> float | None:
    """Wins inside both breakevens — computed as one minus the two tails.

    The whole credit is subtracted at each breakeven, which is how the structure
    actually behaves: only one side can finish in the money, so the side that does
    is cushioned by the entire premium, not half of it.

    `call_vol` defaults to `put_vol` for callers that have only one volatility. On
    an index that default is the pessimistic choice, since put skew means the put
    IV is the higher of the two.
    """
    if short_put >= short_call:
        return None
    if credit < 0:
        # A condor taken on for a debit is not a structure this desk builds, and a
        # negative credit here narrows the profit zone instead of widening it — so
        # the number that came back was not conservative, it was a different
        # structure's answer wearing this one's name.
        #
        # Zero is allowed: it is the un-cushioned limit case, breakevens sitting on
        # the short strikes, and it is how you show what the credit is worth.
        return None
    lower = short_put - credit
    upper = short_call + credit
    if lower >= upper:
        return None
    below = prob_below(spot, lower, dte, put_vol)
    above = prob_above(spot, upper, dte, call_vol if call_vol is not None else put_vol)
    if below is None or above is None:
        return None
    return max(0.0, 1.0 - below - above)


def debit_call_spread(spot: float, long_strike: float, debit: float,
                      dte: int, vol: float) -> float | None:
    """Bull call spread: needs the underlying above the long strike plus the debit."""
    if debit < 0:
        return None
    return prob_above(spot, long_strike + debit, dte, vol)


def debit_put_spread(spot: float, long_strike: float, debit: float,
                     dte: int, vol: float) -> float | None:
    if debit < 0:
        return None
    return prob_below(spot, long_strike - debit, dte, vol)
