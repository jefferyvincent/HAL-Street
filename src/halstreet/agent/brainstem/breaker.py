"""Circuit-breaker state: the things a gate needs to know that a snapshot cannot say.

Every other gate judges a proposal against data the caller just fetched. These four
cannot: whether equity has fallen past today's floor, how many orders went out in the
last hour, whether a human has halted trading. That is *history*, and history has to
live somewhere.

**Why it is not in `gates/`.** The gate layer is pure by contract — no I/O, no clock
beyond an injected date — because that is what makes every gate testable without a
broker. So the state lives here, the loop owns it, and the gates read it off
`GateContext` like any other fact. A gate still cannot reach the filesystem.

**Why it is on disk.** HAL's risk engine keeps this in module-level globals, and
`docs/MIGRATION.md` lists that as one of two defects worth fixing on the way across. A
process-local latch means restarting the agent silently re-arms trading after the
kill switch fired — and restarting is exactly what someone does when an unattended
agent starts behaving oddly. The latch has to outlive the process that set it, or it
is not a latch.

**Entries only.** Nothing here is ever consulted on the way out. When the switch is
latched you want to be *more* able to close, not less; `agent.manager` runs no gates
at all for that reason.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

# How long an entry stays in the rate window.
THROTTLE_WINDOW_S = 3600.0


def _dec(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


@dataclass
class CircuitState:
    """Equity baseline, the halt latch, and recent entry timestamps."""

    path: Path | None = None
    baseline_equity: Decimal | None = None
    baseline_day: str | None = None
    halted: bool = False
    halt_reason: str = ""
    # Unix timestamps of submitted entries, newest last.
    entry_times: list[float] = field(default_factory=list)

    # --- persistence -----------------------------------------------------------

    @classmethod
    def load(cls, path: str | Path | None) -> CircuitState:
        """Read the state, or start fresh. A corrupt file starts fresh and halted.

        Failing *closed* on unreadable state is the only safe choice: the file exists
        to record that trading was stopped, so a file we cannot read might be one
        that says exactly that.
        """
        if path is None:
            return cls()
        p = Path(path)
        if not p.exists():
            return cls(path=p)
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return cls(path=p, halted=True,
                       halt_reason=f"circuit state at {p} is unreadable ({exc}); "
                                   "halted until a human clears it")
        return cls(
            path=p,
            baseline_equity=_dec(raw.get("baseline_equity")),
            baseline_day=raw.get("baseline_day"),
            halted=bool(raw.get("halted")),
            halt_reason=str(raw.get("halt_reason") or ""),
            entry_times=[float(t) for t in raw.get("entry_times") or []],
        )

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "baseline_equity": None if self.baseline_equity is None else str(self.baseline_equity),
            "baseline_day": self.baseline_day,
            "halted": self.halted,
            "halt_reason": self.halt_reason,
            "entry_times": self.entry_times,
        }, indent=2), encoding="utf-8")

    # --- the day's equity floor ------------------------------------------------

    def observe(self, account: dict, *, asof: date | None = None,
                daily_loss_limit_pct: Decimal = Decimal(5)) -> bool:
        """Refresh the baseline and latch the halt if equity has fallen past the floor.

        Returns True on the call that *first* latches, so the caller can react once —
        journal it loudly, drop out of the loop — rather than on every cycle after.

        A new trading day re-baselines and clears the latch. That is deliberate: a
        halt is a stop on *today's* losses, and carrying it forever would need a human
        to notice and clear it before the agent could ever trade again. A halt for any
        other reason clears too, which is the cost of keeping this legible.
        """
        equity = _dec(account.get("equity"))
        if equity is None or equity <= 0:
            return False

        today = (asof or datetime.now(UTC).date()).isoformat()
        if self.baseline_day != today:
            self.baseline_day = today
            self.baseline_equity = equity
            self.halted = False
            self.halt_reason = ""
            self.save()
            return False

        if daily_loss_limit_pct <= 0 or self.baseline_equity is None or self.halted:
            return False

        floor = self.baseline_equity * (1 - daily_loss_limit_pct / 100)
        if equity > floor:
            return False

        loss_pct = (1 - equity / self.baseline_equity) * 100
        self.halted = True
        self.halt_reason = (
            f"daily loss {loss_pct:.1f}% hit the {daily_loss_limit_pct:g}% floor "
            f"(equity ${equity:,.0f} against ${self.baseline_equity:,.0f} at the open)"
        )
        self.save()
        return True

    # --- the rate window -------------------------------------------------------

    def _within(self, now: float) -> list[float]:
        """The stamps still inside the window, without touching the ones that are not.

        Split out from `prune` because two callers want the count and only one of them
        has any business editing the list — see `describe`.
        """
        cutoff = now - THROTTLE_WINDOW_S
        return [t for t in self.entry_times if t >= cutoff]

    def prune(self, now: float) -> None:
        self.entry_times = self._within(now)

    def entries_in_window(self, now: float | None = None) -> int:
        self.prune(now if now is not None else datetime.now(UTC).timestamp())
        return len(self.entry_times)

    def record_entry(self, now: float | None = None) -> None:
        """Stamp a submitted entry so the throttle can count it."""
        stamp = now if now is not None else datetime.now(UTC).timestamp()
        self.prune(stamp)
        self.entry_times.append(stamp)
        self.save()

    # --- human overrides -------------------------------------------------------

    def halt(self, reason: str) -> None:
        self.halted = True
        self.halt_reason = reason
        self.save()

    def clear(self) -> None:
        """Clear the latch. A human act, never something the loop does for itself."""
        self.halted = False
        self.halt_reason = ""
        self.save()

    def describe(self, now: float | None = None) -> str:
        """One line for the startup banner. Reads; never writes.

        It counted `entry_times` raw, and that list is only ever shortened by the two
        methods that prune on their way past — neither of which a freshly loaded state
        has called. So the first thing the agent said about itself, on every run after
        a day that placed an order, was that an entry from yesterday had happened in
        the last hour. Counting the window instead is the fix; counting it *without*
        pruning is the other half, because a diagnostic that edits the throttle's
        state is a second writer of it.
        """
        if self.halted:
            return f"HALTED — {self.halt_reason}"
        if self.baseline_equity is None:
            return "no equity baseline yet"
        recent = self._within(now if now is not None else datetime.now(UTC).timestamp())
        return (f"baseline ${self.baseline_equity:,.0f} on {self.baseline_day}, "
                f"{len(recent)} entr(ies) in the last hour")
