"""cortex — what should we do?

The reasoning stages, and the only place in the agent where a model influences
anything. `llm.py` writes a proposal, `committee.py` runs the catalyst read, the
bull/bear debate and the judge, and `proposal.py` is the schema that narrow opening
speaks through — the parser sits here rather than in a utilities package because a
schema is not a helper, it is the shape of what the model is permitted to say.

Adapted from HAL's `cortex`, which does the same job for the same reason.

Everything here is probabilistic and deliberately small. Read `cerebellum/loop.py` top
to bottom and the model appears exactly once, between two deterministic stages.

**Not here.** Anything that decides whether an order is placed. That is `gates/`, and
keeping it out of this directory is the project's central claim expressed as a
boundary: the model proposes, sixteen deterministic gates dispose. A rule that moved
in here would be a rule an LLM could argue with.
"""
