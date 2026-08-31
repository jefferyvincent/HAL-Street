"""The structure ledger: what the broker cannot tell us.

Alpaca reports positions **netted per contract**. When a vertical and a condor both
sold the Oct-16 770 call, the account showed one `SPY261016C00770000` position at
qty −2 — not two positions tagged to their parents. This was measured, not assumed
(live paper run, 2026-08-26).

The consequence is structural: *the broker has no concept of which structure a leg
belongs to, so the agent cannot read its own state back.* "Close the condor" is a
sentence only our side knows how to express. Nothing downstream — profit targets,
stops, rolls, forced close before expiry — can work without a record of which legs
were opened together and why.

So this module keeps that record, and reconciles it against the flat position list
the broker actually returns.

Reconciliation is the part that matters and the part that is easy to get wrong. The
ledger is a claim about the world; the position list is the world. They diverge for
ordinary reasons — a partial fill, a manual close in the Alpaca dashboard, an
assignment overnight, a leg expiring worthless. When they diverge the **broker wins**,
always, and the divergence is reported rather than silently repaired: an agent that
quietly rewrites its own books to match is an agent that cannot tell you it was wrong.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from halstreet import clock
from halstreet.execution.structures import Side, Structure
from halstreet.marketdata.occ import parse
from halstreet.marketdata.occ import root as occ_root


def _num(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _prices(value: object) -> dict[str, Decimal] | None:
    """A symbol -> price map back off disk, keeping `None` distinct from `{}`.

    A row written before per-leg fills were recorded has no key at all, which must
    read as "never asked" rather than "asked, and there were none" — those are the
    two states the backfill switches on.
    """
    if not isinstance(value, dict):
        return None
    out = {}
    for symbol, price in value.items():
        number = _num(price)
        if number is not None:
            out[str(symbol)] = number
    return out


def _plain_prices(value: dict[str, Decimal] | None) -> dict[str, str] | None:
    """The same map on its way to disk. `Decimal` is not JSON, and `float` is not exact."""
    return None if value is None else {k: str(v) for k, v in value.items()}


@dataclass
class OpenStructure:
    """One structure the agent believes it holds."""

    structure_id: str
    name: str
    underlying: str
    qty: int
    # symbol -> signed contracts this structure contributes (+long, -short)
    legs: dict[str, int]
    opened_at: str
    entry_price: Decimal | None = None
    order_id: str | None = None
    # Why it was opened, carried for the journal and the write-up.
    rationale: str = ""
    closed_at: str | None = None
    exit_price: Decimal | None = None
    #: The closing order, so its fill can be looked up the way the opening one is.
    exit_order_id: str | None = None
    #: Whether each price is a real fill or still the limit it was submitted at.
    #: Both start False: an order is `pending_new` when it is recorded, so the only
    #: number in hand is the limit, and a flag is what lets a later cycle know there
    #: is still something to correct. Without them a fill that happens to equal its
    #: limit is indistinguishable from one that was never looked up at all.
    entry_filled: bool = False
    exit_filled: bool = False
    #: What each leg filled at, per contract, positive on both sides — the broker's
    #: own `legs` array off the order. See `execution.fills.leg_fills`.
    #:
    #: Three states, not two. `None` means the order has never been asked about;
    #: `{}` means it was asked and carried no usable per-leg prices, so it is not
    #: asked again. Without that distinction the backfill either never terminates on
    #: an order that will never have legs, or never starts on a structure recorded
    #: before this field existed — and the live position at the time it was added was
    #: exactly the second case.
    entry_legs: dict[str, Decimal] | None = None
    exit_legs: dict[str, Decimal] | None = None

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    @property
    def nearest_expiry(self) -> date | None:
        expiries = [c.expiry for s in self.legs if (c := parse(s))]
        return min(expiries) if expiries else None

    def dte(self, asof: date | None = None) -> int | None:
        expiry = self.nearest_expiry
        return None if expiry is None else (expiry - (asof or clock.today())).days

    def realized(self) -> Decimal | None:
        """Realized P&L in dollars, once closed.

        Both prices are net per-share debits (positive) or credits (negative), so the
        difference is what the round trip cost or made, times the contract multiplier
        and the size.
        """
        if self.entry_price is None or self.exit_price is None:
            return None
        return (-self.exit_price - self.entry_price) * 100 * self.qty


@dataclass
class Divergence:
    """One contract where the ledger and the broker disagree."""

    symbol: str
    expected: int
    actual: int

    def __str__(self) -> str:
        return f"{self.symbol}: ledger says {self.expected:+d}, broker says {self.actual:+d}"


@dataclass
class Ledger:
    """Structures the agent has opened, persisted as JSON.

    Append-mostly: closing a structure marks it closed rather than deleting it, so the
    run journal and the P&L export can reconstruct the whole session afterwards.
    """

    path: Path
    structures: list[OpenStructure] = field(default_factory=list)

    # --- persistence ----------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path) -> Ledger:
        p = Path(path)
        if not p.exists():
            return cls(path=p)
        raw = json.loads(p.read_text())
        return cls(
            path=p,
            structures=[
                OpenStructure(
                    **{
                        **row,
                        "entry_price": _num(row.get("entry_price")),
                        "exit_price": _num(row.get("exit_price")),
                        "entry_legs": _prices(row.get("entry_legs")),
                        "exit_legs": _prices(row.get("exit_legs")),
                    }
                )
                for row in raw.get("structures", [])
            ],
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = []
        for s in self.structures:
            row = asdict(s)
            row["entry_price"] = None if s.entry_price is None else str(s.entry_price)
            row["exit_price"] = None if s.exit_price is None else str(s.exit_price)
            row["entry_legs"] = _plain_prices(s.entry_legs)
            row["exit_legs"] = _plain_prices(s.exit_legs)
            rows.append(row)
        self.path.write_text(json.dumps({"structures": rows}, indent=2) + "\n")

    # --- recording ------------------------------------------------------------

    def record_open(self, structure: Structure, underlying: str, *,
                    structure_id: str, entry_price: Decimal | None = None,
                    order_id: str | None = None, rationale: str = "") -> OpenStructure:
        """Record a structure the broker has accepted."""
        legs: dict[str, int] = {}
        for leg in structure.legs:
            sign = 1 if leg.side is Side.BUY else -1
            legs[leg.symbol] = legs.get(leg.symbol, 0) + sign * leg.ratio_qty
        entry = OpenStructure(
            structure_id=structure_id,
            name=structure.name,
            underlying=underlying.upper(),
            qty=structure.qty,
            legs=legs,
            opened_at=datetime.now(UTC).isoformat(),
            entry_price=entry_price,
            order_id=order_id,
            rationale=rationale,
        )
        self.structures.append(entry)
        # Persisted here rather than left to the caller. An order accepted by the
        # broker with no ledger record is an untracked position — reconciliation
        # reports it as a divergence forever, and nothing knows what it was meant to
        # be or when to close it. The window between submission and the caller's next
        # save() is small, but it is exactly the window a crash would land in.
        self.save()
        return entry

    def record_fill(self, structure_id: str, fill_price: Decimal) -> bool:
        """Replace a structure's provisional entry price with what it actually filled at.

        Entry price is recorded at submission, when the only number available is the
        *limit* — the order is `pending_new` and has no fill yet. Limits and fills
        differ, and always in a direction that flatters the ledger, because a limit is
        the worst price you were willing to take. The first live round trip opened at
        a limit of -1.59 and filled at -1.60, which is a penny in our favour and a
        dollar of error in the reported P&L of a single contract.

        Returns True when something changed, so the caller can journal a correction
        rather than a no-op.
        """
        for s in self.structures:
            if s.structure_id != structure_id or s.entry_filled:
                continue
            changed = s.entry_price != fill_price
            s.entry_price, s.entry_filled = fill_price, True
            self.save()
            return changed
        return False

    def record_exit_fill(self, structure_id: str, fill_price: Decimal) -> bool:
        """The same correction, on the way out — which nothing was doing.

        `record_fill` above was only ever reached for *open* structures, so a position
        opened and closed inside one session was never corrected at all, and a closing
        order's fill was never fetched under any circumstances. Realized P&L is the
        difference between the two prices, so a round trip could report a figure
        computed from two limits and no fills.

        Not hypothetical: this project's first live round trip was recorded at -1.59
        in and 1.69 out, both `pending_new` with no fill attached, and the reported
        -$10.00 was the difference between two prices nobody traded at. Alpaca's own
        record has the open filling at -1.60; the real loss was $9.00.
        """
        for s in self.structures:
            if s.structure_id != structure_id or s.exit_filled:
                continue
            changed = s.exit_price != fill_price
            s.exit_price, s.exit_filled = fill_price, True
            self.save()
            return changed
        return False

    def forget(self, structure_id: str) -> bool:
        """Remove a structure that never became a position. True if one went.

        Not `record_close`: closing writes an exit price and a realized figure into the
        record, and there is nothing to realize — the order was cancelled, expired or
        rejected, and the account never held it. A cancelled entry left in the book is
        what produced a divergence every cycle that nobody could act on.

        Refuses anything that filled. Deleting a real position from the ledger would
        leave the account holding something the agent has forgotten about, which is the
        worst state in this system.
        """
        for i, s in enumerate(self.structures):
            if s.structure_id != structure_id:
                continue
            if s.entry_filled:
                return False
            del self.structures[i]
            self.save()
            return True
        return False

    def record_close(self, structure_id: str, exit_price: Decimal | None = None,
                     *, exit_order_id: str | None = None) -> None:
        for s in self.structures:
            if s.structure_id == structure_id and s.is_open:
                s.closed_at = datetime.now(UTC).isoformat()
                s.exit_price = exit_price
                # Kept so the closing fill can be looked up on a later cycle the way
                # the opening one is. Without it there is no handle to ask about.
                s.exit_order_id = exit_order_id
                # Same reasoning as record_open, mirrored: a structure whose closing
                # order was accepted must not come back as open after a restart, or
                # the next cycle tries to close it a second time.
                self.save()
                return
        raise KeyError(f"no open structure {structure_id!r} in the ledger")

    # --- views ----------------------------------------------------------------

    @property
    def open_structures(self) -> list[OpenStructure]:
        return [s for s in self.structures if s.is_open]

    def expected_positions(self) -> dict[str, int]:
        """Net contracts per symbol implied by every open structure.

        This is the ledger's prediction of what the broker should report — the same
        netting the broker performs, computed on our side so the two can be compared.
        """
        out: dict[str, int] = {}
        for s in self.open_structures:
            for symbol, signed in s.legs.items():
                out[symbol] = out.get(symbol, 0) + signed * s.qty
        return {k: v for k, v in out.items() if v != 0}

    def contracts_by_underlying(self) -> dict[str, int]:
        """Gross open contracts per underlying, for the concentration gate."""
        out: dict[str, int] = {}
        for symbol, qty in self.expected_positions().items():
            out[occ_root(symbol)] = out.get(occ_root(symbol), 0) + abs(qty)
        return out

    def awaiting_fill_price(self) -> list[OpenStructure]:
        """Structures still carrying a limit where a fill belongs, on either side.

        Open structures need their entry confirmed; closed ones need their exit. Both
        are bounded by the `*_filled` flags, so a structure is asked about until the
        broker answers once, and never again.
        """
        return [
            s for s in self.structures
            if (s.is_open and not s.entry_filled and s.order_id)
            or (not s.is_open and not s.exit_filled and s.exit_order_id)
        ]

    def awaiting_leg_prices(self) -> list[OpenStructure]:
        """Structures whose order has never been asked for its per-leg fills.

        Separate from `awaiting_fill_price` because the two ask about different
        things off the same order. The net price is confirmed once; the per-leg
        prices were not recorded at all until they were wanted for display, so a
        structure can have a confirmed net fill and no legs — which is precisely the
        state every position opened before this existed is in.

        `None` is the only trigger. A structure that was asked and got nothing back
        holds `{}` and is never asked again, so a single-leg order or one the broker
        answers without a `legs` array costs one lookup and not one per cycle for as
        long as it is held.
        """
        return [
            s for s in self.structures
            if (s.is_open and s.entry_legs is None and s.order_id)
            or (not s.is_open and s.exit_legs is None and s.exit_order_id)
        ]

    def record_leg_fills(self, structure_id: str, legs: dict[str, Decimal], *,
                         entry: bool) -> bool:
        """Write the per-leg fills for one side, and stop asking about it.

        `{}` is written as readily as a full map: it is the record that the order was
        looked at and had nothing to give, and it is what bounds `awaiting_leg_prices`.

        Returns whether anything was actually learned, so a caller can journal the
        ones that carried prices and stay quiet about the ones that did not.
        """
        for s in self.structures:
            if s.structure_id != structure_id:
                continue
            if entry:
                s.entry_legs = dict(legs)
            else:
                s.exit_legs = dict(legs)
            self.save()
            return bool(legs)
        return False

    def structures_holding(self, symbol: str) -> list[OpenStructure]:
        """Which open structures contribute to a contract.

        More than one is normal, and is exactly why a netted position cannot be
        attributed to a single parent.
        """
        return [s for s in self.open_structures if symbol in s.legs]

    # --- reconciliation --------------------------------------------------------

    def reconcile(self, positions: list[dict]) -> list[Divergence]:
        """Compare the ledger against the broker's flat position list.

        Returns every disagreement. The caller decides what to do; this function
        deliberately does not repair anything, because a silent repair destroys the
        only evidence that something went wrong.
        """
        if not isinstance(positions, list):
            # Loudly, and here. Iterating a dict yields its keys, so the old failure
            # was an AttributeError inside the loop with no hint that the caller had
            # handed over an unwrapped envelope.
            raise TypeError(
                f"reconcile() wants the broker's position list, got {type(positions).__name__}. "
                "Unwrap the tool envelope first — see mcp_client._rows."
            )
        actual: dict[str, int] = {}
        for position in positions:
            symbol = str(position.get("symbol") or "")
            qty = _num(position.get("qty"))
            if not symbol or qty is None or parse(symbol) is None:
                continue
            actual[symbol] = actual.get(symbol, 0) + int(qty)

        expected = self.expected_positions()
        out: list[Divergence] = []
        for symbol in sorted(set(expected) | set(actual)):
            want, have = expected.get(symbol, 0), actual.get(symbol, 0)
            if want != have:
                out.append(Divergence(symbol, want, have))
        return out

    def mark_closed_where_flat(self, positions: list[dict]) -> list[OpenStructure]:
        """Close out structures whose legs the broker no longer reports at all.

        The ordinary end of a defined-risk position: every leg expired worthless, or
        was closed outside the agent. Only fires when *none* of a structure's legs
        remain — a partially vanished structure is a divergence for a human to look
        at, not something to tidy away.
        """
        live = {
            str(p.get("symbol"))
            for p in positions
            if _num(p.get("qty")) not in (None, Decimal(0))
        }
        closed: list[OpenStructure] = []
        for s in self.open_structures:
            if not any(symbol in live for symbol in s.legs):
                s.closed_at = datetime.now(UTC).isoformat()
                closed.append(s)
        return closed
