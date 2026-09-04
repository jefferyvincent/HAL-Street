"""cerebellum — how is the sequence run?

The learned movement: scan, propose, gate, execute, record, and later decide whether
to get out. `loop.py` is the cycle itself and is the shape of the argument this
project makes; `manager.py` is the exit side, which matters more than entries because
a competition scores P&L over a window and an exit that never happens turns a
defined-risk trade into a full loss.

Coordination, not deliberation. This region invokes the cortex and obeys the gates; it
holds the order of operations and the state machine that carries a structure from
proposal to close.

**Not here.** The reasoning it invokes (`cortex/`), the rhythm it runs on
(`brainstem/schedule.py`), or the record it writes (`telemetry/journal.py`). A cycle
that also decided when to wake up would be two jobs in one file, which is what this
region was carved out of.
"""
