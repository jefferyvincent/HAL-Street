import { useEffect } from "react";
import { KEY, VIEW_KEYS } from "@/constants/keys";
import { useUI } from "@/stores/ui";
import type { Decisions } from "./useDecisions";

/**
 * The keys the footer advertises, and only those.
 *
 * There is no shortcut here that writes anything, because there is nothing to write.
 * The mockup drew F1 PROPOSE and F8 HALT LATCH; both are writes, so both are absent
 * rather than drawn and inert.
 */
export function useShortcuts(decisions: Decisions): void {
  const setView = useUI((s) => s.setView);
  const select = useUI((s) => s.select);
  const { prev, next } = decisions;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      // Never steal a key from a field, in case the panel ever grows one.
      const el = e.target as HTMLElement | null;
      if (el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) return;

      const view = VIEW_KEYS[e.key];
      if (view) return setView(view);
      if (e.key === KEY.prev && prev) return select(prev);
      if (e.key === KEY.next && next) return select(next);
      // null, not the newest ts: "latest" should keep following new pushes rather
      // than pin to whatever happened to be newest when the key was pressed.
      if (e.key === KEY.latest) return select(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [prev, next, setView, select]);
}
