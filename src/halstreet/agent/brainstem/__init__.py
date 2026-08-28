"""brainstem — should we be running at all?

The autonomic layer: the three things that start, stop and pace the organism without
consulting it. `schedule.py` is the body clock — when to scan and when the market is
shut. `lock.py` is one agent per journal, enforced by the filesystem, after two agents
ran against one account for three hours and the only symptom was a scan cadence that
alternated 13m39s and 16m22s. `breaker.py` is the daily-loss halt and the state a gate
cannot compute from a snapshot.

These override deliberation rather than take part in it, which is why they are
together and why none of them imports the cortex. A kill switch with an opinion is
slower than the thing it exists to stop, and `tests/agent/test_regions.py` holds that
edge shut.

`breaker.py` is here rather than in `hippocampus/` because what a module *is* decides
where it lives: a drawdown halt is a reflex, and the fact that it persists its latch
is incidental.

**Not here.** Anything that reasons, and anything that is merely remembered. The
ledger is a memory and lives next door.
"""
