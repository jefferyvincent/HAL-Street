# Plan: <feature>

> **Owner:** Architect · **Phase:** Plan · **Spec:** ./spec.md

## Constitution Check

Run before anything below is written. This gate is the whole point of the plan
document; a plan that skips it is a to-do list.

| Article | Bears on this? | How it is honoured |
|---|---|---|
| I. Paper only | | |
| II. Gates dispose | | |
| III. Exchange clock | | |
| IV. Decimal money | | |
| V. Append-only journal | | |
| VI. Test first | | |
| VII. No false diagnostic | | |
| VIII. No stray English | | |
| IX. Testable placement | | |

**Verdict:** pass | pass with noted deviation | blocked

A deviation is allowed only with a reason recorded here and a test that pins the
deviation's blast radius. "It is faster this way" is not a reason.

## Shape

The modules, hooks or files this touches, and the one-line reason each is the right
home. Name what moves, not just what is added.

## What gets tested, and where

| Behaviour | Test file | Why there |
|---|---|---|

Written before the code, per Article VI. If a row here has no natural home, the shape
above is wrong — fix the shape, not the test.

## Risks

What could be silently wrong after this ships, and what would catch it.
