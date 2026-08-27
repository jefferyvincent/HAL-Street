import { useTranslation } from "react-i18next";
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
 * And a fourth thing on top of the three: whether the record is still current. A
 * session record reports a crossing, not a live reading, so once the agent has
 * exited nothing is left to write the next one — the badge went on saying OPEN into
 * the evening after a run stopped at 15:40. A stale record still shows what it last
 * saw, dimmed and stamped with when, because that is a true statement where a lit
 * OPEN is not.
 */
export function useSession() {
  const t = useStrings();
  const { t: raw } = useTranslation();
  const market = useConnection((s) => s.snapshot?.market ?? null);

  if (!market) {
    return {
      known: false,
      stale: false,
      open: false,
      label: t.chrome.marketUnknown,
      title: raw("chrome.marketTitleUnknown"),
    };
  }
  const open = market.state === "open";
  if (market.stale) {
    return {
      known: true,
      stale: true,
      // Not `open`, whatever the record says. This drives the colour and the dot,
      // and a lit green OPEN is the assertion being withdrawn.
      open: false,
      label: open ? t.chrome.marketWasOpen : t.chrome.marketClosed,
      title: raw("chrome.marketTitleStale", { at: market.at }),
    };
  }
  return {
    known: true,
    stale: false,
    open,
    label: open ? t.chrome.marketOpen : t.chrome.marketClosed,
    title: raw(open ? "chrome.marketTitleOpen" : "chrome.marketTitleClosed",
               { at: market.at }),
  };
}
