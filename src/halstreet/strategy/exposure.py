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

So exposure is derived from the *short* legs, which is where the risk actually
sits in a credit structure, and from their position relative to spot. A short put
below the money profits from price staying up; a short call above it profits from
price staying down; both at once is a range bet.

Long (debit) structures invert, and they are handled even though no profile builds
one today — that is a fact about the current profiles, not about this function,
and the same assumption is what made HAL's per-leg version wrong here.
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

    # Presence of a short leg, not the net. Netting is the trap: a put credit spread
    # is short one put and long another, so its *net* puts are zero and a net-based
    # reading calls a plainly bullish position directionless. The short leg is where
    # the risk is and where the direction is.
    short_puts = any(qty < 0 for c, qty in rights if c.right is Right.PUT)
    short_calls = any(qty < 0 for c, qty in rights if c.right is Right.CALL)
    if short_puts and short_calls:
        return NEUTRAL
    if short_puts:
        return BULLISH
    if short_calls:
        return BEARISH

    # Nothing short: a debit structure, where the long legs carry the direction.
    long_calls = any(qty > 0 for c, qty in rights if c.right is Right.CALL)
    long_puts = any(qty > 0 for c, qty in rights if c.right is Right.PUT)
    if long_calls and long_puts:
        return NEUTRAL          # a straddle or strangle; no directional opinion
    if long_calls:
        return BULLISH
    if long_puts:
        return BEARISH
    return UNKNOWN


def agrees(exposure: str, side: str) -> bool | None:
    """Whether a pattern's side runs with the position. `None` when neither says.

    Three-valued because "no opinion" and "disagrees" are different facts and the
    badge shows them differently — a neutral pattern against a directional position
    is not a warning, and a directional pattern against a condor is not either.
    """
    if exposure in (NEUTRAL, UNKNOWN) or side == NEUTRAL:
        return None
    return exposure == side
