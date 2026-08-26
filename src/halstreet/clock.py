"""What day it is on the exchange, which is not always what day it is here.

Nine places in this codebase called `datetime.date.today()`, and every one of them was
asking a question about the *market*: how many days until this contract expires, has
the daily-loss baseline rolled over, is this position inside the force-close window.
`today()` answers a question about the machine — it reads the host's local calendar,
which is a fact about where a server happens to be plugged in.

Those agree most of the time, which is what makes it dangerous. Run the agent on a UTC
box after 8pm New York and the two dates differ; every DTE is off by one, the DTE floor
admits contracts a day nearer expiry than it believes, and the breaker thinks a new
session has begun while the exchange is mid-afternoon. Nothing errors. The numbers are
just quietly wrong, and only outside US business hours — which is exactly when nobody
is watching.

**The broker is asked, not a timezone table.** Alpaca's clock endpoint returns its
timestamp in exchange-local time with the offset attached
(`2026-08-26T17:19:17-04:00`), so the session date is `timestamp.date()` and nothing
here needs to know that the exchange is in New York, when it observes daylight saving,
or what its hours are. If the exchange moved, or a second venue were added, this would
follow without an edit. A hardcoded `ZoneInfo("America/New_York")` would be a second
claim about the world to keep in sync with the first.

**A fallback that hides is worse than no fallback.** When the clock has not been
adopted — a unit test, a CLI run that never reached the broker — this returns the local
date and *counts* it. `fallbacks()` is journalled at the end of every cycle, so a run
that computed a DTE from the host calendar says so in the record rather than looking
identical to one that did not.
"""

from __future__ import annotations

import threading
from datetime import date, datetime
from typing import Any

_lock = threading.Lock()
_session: date | None = None
_source: str = "unset"
_fallbacks = 0


def adopt(clock: Any) -> date | None:
    """Take the session date from the broker's own clock. Returns it, or None.

    Accepts anything with a `timestamp` — a `MarketClock`, or a raw payload dict — so
    the caller does not have to reach into the scheduler's types to set it.
    """
    stamp = getattr(clock, "timestamp", None)
    if stamp is None and isinstance(clock, dict):
        raw = clock.get("timestamp")
        try:
            stamp = datetime.fromisoformat(str(raw)) if raw else None
        except (TypeError, ValueError):
            stamp = None
    if not isinstance(stamp, datetime):
        return None

    with _lock:
        global _session, _source
        _session = stamp.date()
        _source = "broker"
    return _session


def today() -> date:
    """The exchange's date if the broker has told us, otherwise the host's — counted.

    Every `date.today()` in the trading path now comes through here, so there is one
    place that knows whether the answer is authoritative and one number that says how
    often it was not.
    """
    with _lock:
        if _session is not None:
            return _session
        global _fallbacks
        _fallbacks += 1
    # The one deliberate read of the host calendar in the codebase, which is why
    # every other one is now a lint error. It is counted above, so a run that
    # reached here says so in its journal.
    return date.today()  # noqa: DTZ011


def fallbacks() -> int:
    """How many times the host calendar stood in for the exchange's."""
    with _lock:
        return _fallbacks


def source() -> str:
    return _source


def describe() -> str:
    with _lock:
        if _session is None:
            return f"session date unset — {_fallbacks} local-calendar fallback(s)"
        note = f", {_fallbacks} fallback(s) before it was adopted" if _fallbacks else ""
        return f"session date {_session.isoformat()} from the broker{note}"


def reset() -> None:
    """Forget the adopted date. For tests, and for a process that changes accounts."""
    with _lock:
        global _session, _source, _fallbacks
        _session, _source, _fallbacks = None, "unset", 0
