# Spec: <feature>

> **Owner:** Analyst → PM · **Phase:** Specify · **Status:** draft | clarified | planned
> **Surface:** python | ux | both

## Why this exists

The failure, in one paragraph. What is wrong today, what it costs, and how it shows up
to whoever is looking at the screen or reading the journal. If you cannot name the
failure, you are describing a preference and this is the wrong document.

## What must become true

Numbered, observable, and written so a test can be pointed at each one.

1. …
2. …

## Out of scope

What a reader would reasonably assume is included and is not. This section is what
stops a plan from growing.

## Behaviour

For **ux**: what appears on screen, in which state, with which words — by string key,
not by English. Include the empty case, the null case, and the stale case.

For **python**: what the function returns, and what it returns when the input is
unreadable. "Unreadable" is never "zero" (Constitution VII).

## Open questions

| # | Question | Blocks | Answer |
|---|---|---|---|

A spec with an unanswered question that blocks a numbered requirement does not go to
Plan. Answer it or cut the requirement.

## Constitution notes

Any article that bears on this feature, and how it is honoured. If none apply, say so
explicitly — that sentence is the evidence the check was actually run.
