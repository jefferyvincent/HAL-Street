"""Which family a structure belongs to, read off its legs.

The ledger records legs and a name. The name is prose built for a human — "2026-10-16
765/775 call credit spread" — and parsing prose to make a trading decision is how a
rename becomes a bug. The legs are the fact, so this reads those.

It exists for the loss cooldown, which keys on *what was traded* rather than only on
the underlying. Losing three times selling calls into a rally says nothing about
whether a put spread on the same name is a bad idea, and a cooldown that benched the
whole symbol would be throwing away the half of the book that was never tested.
"""

from __future__ import annotations

from halstreet.marketdata.occ import Right, parse
from halstreet.strategy.profiles import CALL_CREDIT, IRON_CONDOR, PUT_CREDIT

#: The bucket for a shape this module does not recognise.
#:
#: A name rather than `None`, and that is deliberate. A structure whose family cannot
#: be read still has a P&L, and a losing streak that quietly skipped it would be a
#: cooldown with a hole in it — in exactly the trades nobody anticipated, which are
#: the ones worth noticing. Lumping unrecognised shapes together can only bench
#: sooner, which is the safe direction for a rule whose job is to stop losing.
OTHER = "other"


def classify(legs: dict[str, int]) -> str:
    """The family these legs form. Never raises, never returns `None`.

    Shape only: two puts are a put spread whatever the strikes, and quantity is
    ignored entirely, because a two-contract spread is the same idea as a
    one-contract spread. A cooldown keyed on a size-sensitive family would let the
    same losing trade back in at a different quantity.

    This project sells premium, so the vertical families are named for credit. A debit
    vertical would classify the same way — it is the same shape — and that is
    acceptable here: the cooldown asks "have we been wrong about calls on this name",
    which is a question about direction and instrument rather than about sign.
    """
    rights = [parse(symbol) for symbol in legs]
    if any(contract is None for contract in rights):
        return OTHER

    calls = sum(1 for c in rights if c is not None and c.right is Right.CALL)
    puts = sum(1 for c in rights if c is not None and c.right is Right.PUT)

    if calls == 2 and puts == 2:
        return IRON_CONDOR
    if calls == 2 and puts == 0:
        return CALL_CREDIT
    if puts == 2 and calls == 0:
        return PUT_CREDIT
    return OTHER
