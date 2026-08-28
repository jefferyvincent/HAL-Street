import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

/**
 * The session badge's content, derived rather than assembled in the component.
 *
 * Three states, not two. "Unknown" is its own answer: the market record only exists
 * once a scheduled run has written a boundary, and a `--once` run never observes the
 * closed half. Collapsing unknown into closed would have the panel assert a session
 * had ended when nothing ever said so.
 *
 * The server decides *what* the market is doing, including when it had to work that
 * out from a broker-published boundary nobody wrote down. This decides how loudly to
 * say it. A state inferred from the broker's own next-close is a fact and reads as
 * one; only `last-seen` — nothing writing and no boundary to reason from — is hedged.
 */
export function useSession() {
  const t = useStrings();
  const market = useConnection((s) => s.snapshot?.market ?? null);

  if (!market) {
    return {
      known: false,
      certain: false,
      open: false,
      label: t.chrome.marketUnknown,
      title: t.chrome.marketTitleUnknown,
    };
  }

  const open = market.state === "open";
  const label = open ? t.chrome.marketOpen : t.chrome.marketClosed;

  // Nothing is writing, but the broker had already published when this session ends
  // and that time is still ahead. The same figure that lets a passed close say CLOSED
  // lets an unreached one say OPEN — it was only ever read in one direction, so a
  // console watching a stopped agent at 15:50 hedged OPEN with a question mark while
  // the 16:00 close sat unused in the record it was hedging.
  //
  // The agent's silence is a separate fact and the console states it separately.
  if (market.source === "published") {
    return {
      known: true,
      certain: true,
      open,
      label,
      title: t.chrome.marketTitlePublished(market.until ?? ""),
    };
  }

  // Nothing is writing and no boundary to reason from in either direction. This is
  // the only case where the panel genuinely does not know, and the only one that
  // hedges.
  if (market.source === "last-seen") {
    return {
      known: true,
      certain: false,
      // Not `open` whatever the record says: this drives the colour, and a lit green
      // OPEN is exactly the assertion being withdrawn.
      open: false,
      label,
      title: t.chrome.marketTitleLastSeen(market.at),
    };
  }

  return {
    known: true,
    certain: true,
    open,
    title: market.source === "boundary"
      ? t.chrome.marketTitleBoundary(market.crossed_at ?? "")
      : open
        ? t.chrome.marketTitleOpen(market.at)
        : t.chrome.marketTitleClosed(market.at),
    label,
  };
}
