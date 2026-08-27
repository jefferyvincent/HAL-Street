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
 */
export function useSession() {
  const t = useStrings();
  const { t: raw } = useTranslation();
  const market = useConnection((s) => s.snapshot?.market ?? null);

  if (!market) {
    return {
      known: false,
      open: false,
      label: t.chrome.marketUnknown,
      title: raw("chrome.marketTitleUnknown"),
    };
  }
  const open = market.state === "open";
  return {
    known: true,
    open,
    label: open ? t.chrome.marketOpen : t.chrome.marketClosed,
    title: raw(open ? "chrome.marketTitleOpen" : "chrome.marketTitleClosed",
               { at: market.at }),
  };
}
