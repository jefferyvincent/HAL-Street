# apps/desktop — rules

Three rules govern every file under `src/`. They are not style preferences; a change
that breaks one of them is wrong even if it renders correctly.

## 1. Business logic lives in its own hook

Anything that is not markup belongs in `src/hooks/`, one hook per concern, named
`useThing.ts`. That includes fetching and polling, subscriptions and timers, derived
or aggregated values, sorting and grouping, formatting decisions, state machines, and
any conditional that answers "what should be shown" rather than "how should it look".

A hook returns data. It does not return JSX, and it does not know which component
consumes it. Pure helpers with no React in them go to `src/lib/` instead —
`src/lib/` is where the unit tests live, and a rule worth a test belongs there with
the hook calling it.

One thing a component may call directly: a **pure display helper** that renders a
value it was already handed — `f.money(x)` from `useFormat()`, `stripRoot`, `hueOf`.
The line is what the call decides. Rendering a figure is presentation; choosing
*which* figure, or whether to show it at all, is a rule, and rules go in the hook.

`src/stores/` holds shared state (zustand). A hook may read from it; a component
reads a store only for a plain value it renders directly.

## 2. JSX and business logic never share a file

A component in `src/components/` or `src/views/` is a template. Its body is a short
list of hook calls followed by a `return` of markup. Nothing else.

Allowed in a component: `useStrings()` and other hook calls, destructuring what they
return, ternaries and `.map()` inside the JSX that pick between rendered shapes, and
`className` composition via `cn`.

Not allowed in a component: `useEffect`, `useMemo`, `useState` holding derived data,
`fetch`, `setInterval`, arithmetic on domain values, date maths, sorting, filtering
that encodes a rule, or a helper function declared in the file. If you are about to
write one of those, the file you want is a hook.

When a component grows a condition worth naming, name it in the hook and return a
boolean. `if (positions.length === 0)` is fine. `if (p.qty > 0 && p.mark && ageMs <
STALE)` is a rule, and rules live in hooks.

`Holding.tsx`/`useHolding.ts` and `Sparkline.tsx`/`useSparkline.ts`/`lib/spark.ts`
are the reference shapes: the component is markup, the hook decides, the arithmetic
is pure and tested.

## 3. Strings belong in the constants file, then get translated

No user-facing literal appears in `components/`, `views/`, or `hooks/`. Ever. That
includes labels, empty states, units, `title=` tooltips, `aria-label`, and error
text.

Adding a string is three edits, in this order:

1. `src/locales/en.json` — the English words, under the section that owns them.
   Interpolate with named variables: `"Last seen at {{at}}"`. Never concatenate.
2. `src/constants/strings.ts` — the key, in `makeStrings`. Plain strings are
   `t("chrome.equity")`; anything with a variable in it is a function taking named
   variables, so a translation can reorder the sentence.
3. The component — `const t = useStrings()`, then `{t.chrome.equity}`.

Every other locale file is a sibling of `en.json` with the same key shape, so a new
key must be reachable by key alone and never assume English word order.

Numbers and dates are formatted by `src/lib/format.ts`, not written into the words —
and `format.ts` itself holds **no English**. The words a formatter puts around a
figure ("credit", "to close", "just now", the dash for a missing number) come from
the `format` section of the string table, through `useFormat()`. Anything spelled in
`lib/` is a translation hole no locale file can reach.

The same goes for glyphs the markup used to own: the em dash, the "·" between
counts, the separator in a joined list. They are `t.common.*`, because a locale
punctuates a list its own way.

## 4. Test first, always

Write the failing test, then write the code that passes it. Not the other way round,
and not "I will add tests after" — a test written after the fact tests what the code
does, which is the one thing you already know.

The order, every time:

1. **Write the test.** Name the behaviour, not the function: `it("draws nothing from
   one reading")`, not `it("returns null")`. State *why* in a comment where the
   answer is non-obvious — the tests in `src/lib/` are the closest thing this panel
   has to a specification of what its numbers mean.
2. **Run it and watch it fail** — `npm test`. A test that passes before the code
   exists is testing nothing, and that is worth ten seconds to find out.
3. **Write the smallest code that passes it.**
4. **Run the whole suite**, not just the new file.

Tests live beside what they test: `src/lib/spark.ts` and `src/lib/spark.test.ts`.
Vitest, no DOM — which is exactly why rules 1 and 2 exist. A rule that lives in a
hook or a component cannot be reached from a test without mounting React; the same
rule as a pure function in `src/lib/` is three lines to assert. **If something is
awkward to test, that is the design telling you the logic is in the wrong file.**
Push it down into `lib/`, call it from the hook, and test it there.

What has to be covered: every branch a person could get wrong. The empty case, the
null case, the zero case, the sign, the boundary. `sparkGeometry` has a test for one
point, for a flat line, and for a line that never crossed zero — three answers that
each looked like an edge case and each turned out to be the common one.

**`npm test` must be green before any piece of work is finished.** Not skipped, not
commented out, not "failing for an unrelated reason" — green. If a test fails, the
change is not done, and reporting it as done is worse than not having written it.
