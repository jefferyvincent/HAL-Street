/**
 * Join class names, dropping anything falsy — and let the last text colour win.
 *
 * The join alone was not enough, and the bug it caused is the ordinary one for this
 * pattern. A shared cell component carried `text-ink/75` in its base string and its
 * caller passed `text-fail` for a loss; both reached the element, neither is more
 * specific than the other, and which one paints is decided by the order Tailwind
 * happened to emit them in the stylesheet. Grey won, so every negative leg P&L in the
 * panel rendered grey — silently, and only for that one component.
 *
 * `tailwind-merge` is the usual answer and is a dependency and a large one. This does
 * the one thing that was actually going wrong: among classes that set a *text colour*,
 * keep only the last. Nothing else is touched, so the order of every other class is
 * preserved exactly.
 *
 * The match is deliberately narrow — a colour token from the palette, optionally with
 * an opacity suffix. `text-[11px]`, `text-right`, `text-wrap` and `text-balance` do
 * not look like that and are never dropped, which is the failure mode a hand-rolled
 * merge usually has.
 */

//: The palette from `globals.css`, plus the aliases the theme defines on top of it.
//: A colour utility this does not recognise is left alone rather than guessed at —
//: the cost of missing one is the old behaviour, and the cost of over-matching is a
//: size or an alignment being silently discarded.
const COLORS = [
  "void", "chrome", "panel", "sunk", "raise", "line", "line-soft", "edge",
  "ink", "amber", "pass", "fail", "fail-ink", "agent", "mute", "faint",
  "current", "inherit", "transparent", "white", "black",
];

const COLOR_CLASS = new RegExp(`^text-(${COLORS.join("|")})(/\\d{1,3})?$`);

export const cn = (...parts: (string | false | null | undefined)[]): string => {
  const classes = parts.filter(Boolean).join(" ").split(/\s+/).filter(Boolean);
  const last = classes.map((c) => COLOR_CLASS.test(c)).lastIndexOf(true);
  return (last === -1
    ? classes
    : classes.filter((c, i) => i === last || !COLOR_CLASS.test(c))
  ).join(" ");
};
