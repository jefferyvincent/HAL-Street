/**
 * Formatting only. Nothing here computes a figure — it renders one the server sent.
 *
 * Every money value arrives as a decimal string. These helpers parse at the edge, for
 * display, and never write a float back into anything the panel keeps.
 */

export const money = (v: string | number | null | undefined, dp = 2): string => {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
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
export const premium = (v: string | number | null | undefined, dp = 2): string => {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  if (n === 0) return money(0, dp);
  return `${money(Math.abs(n), dp)} ${n < 0 ? "credit" : "debit"}`;
};

/**
 * A mark, which is what it would cost to close — the number the exit policy watches.
 *
 * Same convention, same problem: a credit spread marked at -1.635 is one you can buy
 * back for $1.64, and it is *winning* as that falls toward zero. "-$1.64" says none
 * of that.
 */
export const toClose = (v: string | number | null | undefined, dp = 2): string => {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return `${money(Math.abs(n), dp)} to close`;
};

/** How long ago, in words, for a number that is a scan old rather than live. */
export const ago = (t?: string | null): string => {
  if (!t) return "";
  const seconds = Math.max(0, (Date.now() - new Date(t).getTime()) / 1000);
  if (seconds < 90) return "just now";
  const minutes = Math.round(seconds / 60);
  return minutes < 60 ? `${minutes}m ago` : `${Math.round(minutes / 60)}h ago`;
};

export const plain = (v: string | number | null | undefined, dp = 2): string => {
  const n = Number(v);
  return Number.isFinite(n)
    ? n.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp })
    : "—";
};

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
