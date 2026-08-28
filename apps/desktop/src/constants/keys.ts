/**
 * The keys the panel binds, in one place.
 *
 * The footer used to spell "J", "K", "L" and 1–5 in its own markup while
 * `useShortcuts` bound them separately, so the advertised keys and the working keys
 * were two lists that agreed by hand. They are one list now: a binding that moves
 * moves the legend with it.
 *
 * Nothing here writes. There is no key for propose or halt because the panel cannot
 * do either — an advertised key that does nothing is the same lie as a dead tab.
 */

import type { View } from "@/stores/ui";

export const KEY = {
  prev: "j",
  next: "k",
  latest: "l",
} as const;

/** Digit to view, in the order the tabs sit in. */
export const VIEW_KEYS: Record<string, View> = {
  "1": "console",
  "2": "journal",
  "3": "gates",
  "4": "committee",
  "5": "book",
};
