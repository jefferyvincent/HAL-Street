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
