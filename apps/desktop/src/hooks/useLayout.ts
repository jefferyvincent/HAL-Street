import { useUI, type View } from "@/stores/ui";

/**
 * Which view is up, and whether it keeps the rails.
 *
 * The rails describe the *selected decision*, so they belong to the console. The
 * other views take the full width rather than compete with a narrower copy of
 * themselves down the right-hand side.
 */
export function useLayout(): { view: View; rails: boolean } {
  const view = useUI((s) => s.view);
  return { view, rails: view === "console" };
}
