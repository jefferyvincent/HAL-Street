"""hippocampus — what happened, and what are we holding?

Recall. `ledger.py` is what the broker cannot tell us: Alpaca reports positions netted
per contract, so when a vertical and a condor both sold the Oct-16 770 call the
account showed one position at a net quantity and neither structure could be found in
it. The ledger is the agent's own record of the structures behind that number.
`soak.py` reads a finished session back out of its journal and says which lifecycle
events it actually reached. `experience.py` answers the third recall question — what
has this desk been getting wrong lately — by walking the ledger's closed structures
for runs of losses on one underlying and structure family.

All three are reconstruction: taking a record and answering what it means now.
`experience.py` in particular stores nothing of its own, because a second file
tracking losing streaks would be a second claim to keep in step with the ledger, and
the day they disagreed the agent would bench a pair that had just won.

**Not here.** `telemetry/journal.py`, which is the write side and the panel's source —
the record itself, not the agent recalling it. And nothing that decides anything: a
memory that also acted would make every read a side effect.
"""
