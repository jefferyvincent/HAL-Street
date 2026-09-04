import { describe, expect, it } from "vitest";
import { cn } from "./cn";

/**
 * The bug these exist for: a shared cell carried `text-ink/75` in its base string and
 * its caller passed `text-fail` for a loss. Both reached the element, neither is more
 * specific, and stylesheet order decided. Grey won — so every negative leg P&L in the
 * panel rendered grey, silently, and only in that one component.
 */
describe("the last text colour wins", () => {
  it("drops a base colour when the caller supplies one", () => {
    expect(cn("text-ink/75 tabular-nums", "text-fail")).toBe("tabular-nums text-fail");
  });

  it("keeps the last of several", () => {
    expect(cn("text-ink", "text-pass", "text-fail")).toBe("text-fail");
  });

  it("leaves a lone colour exactly where it was", () => {
    expect(cn("font-mono text-ink/40 leading-none")).toBe("font-mono text-ink/40 leading-none");
  });

  it("handles opacity suffixes on either side", () => {
    expect(cn("text-ink/75", "text-fail/70")).toBe("text-fail/70");
    expect(cn("text-fail/70", "text-ink")).toBe("text-ink");
  });
});

describe("what it must never touch", () => {
  // The usual failure of a hand-rolled merge: matching `text-` too eagerly and
  // silently discarding a font size, which is invisible until someone looks.
  it.each([
    "text-[11px]", "text-[9.5px]", "text-right", "text-left", "text-center",
    "text-wrap", "text-balance", "text-nowrap", "text-ellipsis",
  ])("keeps %s beside a colour", (other) => {
    expect(cn(`${other} text-ink`, "text-fail").split(" ")).toContain(other);
  });

  it("keeps a size when it is the only text- class", () => {
    expect(cn("text-[13px]", "font-bold")).toBe("text-[13px] font-bold");
  });

  it("leaves an unrecognised colour alone rather than guessing", () => {
    // Costs the old behaviour, which is a grey number. Over-matching costs a
    // silently dropped size, which is worse and harder to see.
    expect(cn("text-ink", "text-brandnew")).toBe("text-ink text-brandnew");
  });

  it("never touches a prefixed colour, which is a different rule entirely", () => {
    // `hover:text-ink` beside `text-ink/40` is the normal way to write a hover state.
    // Dropping either would break every link and button in the panel.
    expect(cn("text-ink/40 hover:text-ink", "text-fail"))
      .toBe("hover:text-ink text-fail");
    expect(cn("focus-visible:text-amber", "text-ink"))
      .toBe("focus-visible:text-amber text-ink");
    expect(cn("min-[1181px]:text-pass text-ink")).toBe("min-[1181px]:text-pass text-ink");
  });

  it("preserves the order of everything else", () => {
    expect(cn("a b", "c", "d")).toBe("a b c d");
  });
});

describe("the joining it always did", () => {
  it("drops falsy parts", () => {
    expect(cn("a", false, null, undefined, "b")).toBe("a b");
  });

  it("collapses stray whitespace", () => {
    expect(cn("  a   b  ", " c ")).toBe("a b c");
  });

  it("is empty for nothing", () => {
    expect(cn()).toBe("");
    expect(cn(false, null)).toBe("");
  });
});
