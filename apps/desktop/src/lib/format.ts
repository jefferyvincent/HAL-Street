/**
 * Formatting only. Nothing here computes a figure — it renders one the server sent.
 *
 * Every money value arrives as a decimal string. These helpers parse at the edge, for
 * display, and never write a float back into anything the panel keeps.
 *
 * **No English lives here.** A premium is "$1.51 credit" in one locale and something
 * else in another, and a formatter that spelled it would be a translation hole no
 * `locales/*.json` could reach. So the words are passed in — `makeFormat` takes them
 * from `constants/strings.ts` — and this file holds only the arithmetic of display:
 * where the sign goes, how many places, which figure is absolute. Callers reach it
 * through `useFormat()`.
 */

/** The words the formatters put around a number, from the string table. */
export interface FormatWords {
  dash: string;
  credit: (amount: string) => string;
  debit: (amount: string) => string;
  toClose: (amount: string) => string;
  justNow: string;
  minutesAgo: (n: number) => string;
  hoursAgo: (n: number) => string;
}

export const clock = (t?: string | null): string =>
  t ? new Date(t).toLocaleTimeString([], { hour12: false }) : "";

export const day = (t?: string | null): string =>
  t ? new Date(t).toLocaleDateString([], { month: "short", day: "numeric" }) : "";

/**
 * Gate reasons are full sentences; the ledger column has room for the number in them.
 * The full text stays in the row's title attribute, so nothing is actually lost.
 */
export const short = (reason: string | undefined, max = 22): string => {
  const r = String(reason ?? "");
  const m =
    r.match(/[\d.,$%+−-]+\s*(?:\/|of|vs)\s*[\d.,$%]+/i) ??
    r.match(/^[A-Za-z ]{0,18}[\d.,$%+-]+[^,;.]{0,10}/);
  const out = (m ? m[0] : r).trim();
  return out.length > max ? out.slice(0, max - 1) + "…" : out;
};

/** The formatters, bound to one locale's words. Built once per language change. */
export function makeFormat(w: FormatWords) {
  const money = (v: string | number | null | undefined, dp = 2): string => {
    const n = Number(v);
    if (!Number.isFinite(n)) return w.dash;
    return (
      (n < 0 ? "-$" : "$") +
      Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp })
    );
  };

  /**
   * A premium, said the way a desk says it.
   *
   * Prices here are *position values* on one sign convention — negative means the
   * structure is held for a credit — which is right internally and reads as a loss on
   * a screen. A spread opened at -1.51 was opened for $1.51 of credit received, and
   * rendering that as "-$1.51" beside a P&L column invites exactly the wrong reading.
   *
   * The sign is not flipped anywhere; only the label changes.
   */
  const premium = (v: string | number | null | undefined, dp = 2): string => {
    const n = Number(v);
    if (!Number.isFinite(n)) return w.dash;
    if (n === 0) return money(0, dp);
    const amount = money(Math.abs(n), dp);
    return n < 0 ? w.credit(amount) : w.debit(amount);
  };

  /**
   * A mark, which is what it would cost to close — the number the exit policy watches.
   *
   * Same convention, same problem: a credit spread marked at -1.635 is one you can buy
   * back for $1.64, and it is *winning* as that falls toward zero. "-$1.64" says none
   * of that.
   */
  const toClose = (v: string | number | null | undefined, dp = 2): string => {
    const n = Number(v);
    if (!Number.isFinite(n)) return w.dash;
    return w.toClose(money(Math.abs(n), dp));
  };

  /** How long ago, in words, for a number that is a scan old rather than live. */
  const ago = (t?: string | null): string => {
    if (!t) return "";
    const seconds = Math.max(0, (Date.now() - new Date(t).getTime()) / 1000);
    if (seconds < 90) return w.justNow;
    const minutes = Math.round(seconds / 60);
    return minutes < 60 ? w.minutesAgo(minutes) : w.hoursAgo(Math.round(minutes / 60));
  };

  const plain = (v: string | number | null | undefined, dp = 2): string => {
    const n = Number(v);
    return Number.isFinite(n)
      ? n.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp })
      : w.dash;
  };

  /**
   * The same, with the sign always shown.
   *
   * For figures whose direction is the point — a move on the equity header, a leg's
   * signed contracts. `signDisplay` rather than a "+" glued on the front, so a locale
   * that puts the sign elsewhere still gets it right.
   */
  const signed = (v: string | number | null | undefined, dp = 2): string => {
    const n = Number(v);
    return Number.isFinite(n)
      ? n.toLocaleString(undefined, {
          minimumFractionDigits: dp, maximumFractionDigits: dp, signDisplay: "always",
        })
      : w.dash;
  };

  return { money, premium, toClose, ago, plain, signed, clock, day, short, dash: w.dash };
}

export type Format = ReturnType<typeof makeFormat>;
