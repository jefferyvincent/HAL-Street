"""Which way an open structure wants the underlying to go.

Adapted from HAL's `position_watch.exposure_side`, and the adaptation is the whole
of the work. HAL holds single instruments, so the question is a property of one
leg: a long call is bullish, a long put bearish, and shorting inverts it. That
function is four lines and it is right.

Nothing here is one leg. Every structure this agent builds is a spread, and the
naive per-leg reading gets all three of them wrong:

  * A **put credit spread** is short a put and long a further put. Read leg by leg
    that is "bearish and bearish". It is a **bullish** position — you keep the
    credit if the underlying stays up.
  * A **call credit spread** is the mirror, and reads "bullish" leg by leg while
    being bearish.
  * An **iron condor** is all four at once and is directionally **neutral**: it
    wants price to go nowhere, which is not an answer any per-leg rule can produce
    because it is a property of the combination.

So exposure is derived from the **strikes**, one right at a time: within a right,
the long leg at the lower strike is bullish, and two rights pointing opposite ways
is a range bet.

That rule replaced one that read the short leg. Reading the short leg is correct
for every credit structure and exactly wrong for a debit one — a call debit spread
is short a call and is bullish — and when the long verticals arrived on
2026-09-02 it had both of them backwards. The strike rule covers all four
verticals and does not care how the structure was paid for.
"""

from __future__ import annotations

from decimal import Decimal

from halstreet.marketdata.occ import Right, parse

BULLISH = "bullish"
BEARISH = "bearish"
NEUTRAL = "neutral"
UNKNOWN = "unknown"


def exposure_of(legs: dict[str, int], *, spot: Decimal | None = None) -> str:
    """`bullish` / `bearish` / `neutral` / `unknown` for a whole structure.

    `legs` maps OCC symbol to signed contracts, positive long and negative short —
    the ledger's own shape, so this reads what the agent actually holds rather than
    what it meant to hold.

    `unknown` when nothing is parseable. Not a shrug: a badge that guesses a
    direction is worse than one that admits it cannot say, because a wrong
    direction turns a confirming pattern into a warning and the reader stops
    believing any of them.
    """
    rights = [(parse(symbol), qty) for symbol, qty in legs.items()]
    rights = [(c, qty) for c, qty in rights if c is not None]
    if not rights:
        return UNKNOWN

    # Read one right at a time, then combine. Netting across the whole structure is
    # the trap: a put credit spread is short one put and long another, so its *net*
    # puts are zero and a net-based reading calls a plainly bullish position
    # directionless.
    sides = {side for right in (Right.PUT, Right.CALL)
             if (side := _side_of(rights, right)) is not None}
    if not sides:
        return UNKNOWN
    if len(sides) > 1:
        # A condor, a straddle, a strangle: two rights pointing opposite ways. The
        # structure wants neither, which is not an answer any single-leg rule produces.
        return NEUTRAL
    return sides.pop()


def _side_of(rights: list[tuple], right: Right) -> str | None:
    """Which way this structure's legs in one right lean. `None` if it holds none.

    **The long leg at the lower strike is bullish.** One rule for all four verticals,
    and it falls out of what a vertical is rather than out of how it was paid for.

    The earlier rule read the *short* leg, on the reasoning that a credit structure
    carries its risk there. That was true of every structure this agent could build,
    and exactly wrong for the two it gained on 2026-09-02: a call debit spread is short
    a call and is bullish, and reading the short leg put "WANTS SPY DOWN" on a position
    wanting the opposite — which turns every confirming pattern into a warning and
    teaches a reader to stop believing the badge.

    A bare leg has no other strike to compare against, so it falls back to what a
    single option means: long a call or short a put is bullish, and the mirror bearish.

    Both legs at one strike is not a vertical. Whatever it is, no direction can be read
    off it, and inventing one is worse than admitting it.
    """
    legs = [(c.strike, qty) for c, qty in rights if c.right is right]
    if not legs:
        return None

    longs = [strike for strike, qty in legs if qty > 0]
    shorts = [strike for strike, qty in legs if qty < 0]
    if longs and shorts:
        low_long, low_short = min(longs), min(shorts)
        if low_long == low_short:
            return None
        return BULLISH if low_long < low_short else BEARISH

    # A bare leg, or several on one side only.
    if longs:
        return BULLISH if right is Right.CALL else BEARISH
    return BEARISH if right is Right.CALL else BULLISH


def agrees(exposure: str, side: str) -> bool | None:
    """Whether a pattern's side runs with the position. `None` when neither says.

    Three-valued because "no opinion" and "disagrees" are different facts and the
    badge shows them differently — a neutral pattern against a directional position
    is not a warning, and a directional pattern against a condor is not either.
    """
    if exposure in (NEUTRAL, UNKNOWN) or side == NEUTRAL:
        return None
    return exposure == side
