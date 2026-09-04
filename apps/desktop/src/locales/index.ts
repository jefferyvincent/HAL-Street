/**
 * The translation bundles.
 *
 * One JSON file per language, each a mirror of `en.json`'s key tree. Adding a
 * language is adding a file and a line here — no component, hook or type changes,
 * because the components ask `useStrings()` for their words rather than spelling
 * them, and the key tree that hook reads is the same for every locale.
 */

import en from "./en.json";

export const LOCALES = { en } as const;
export type Locale = keyof typeof LOCALES;
export const DEFAULT_LOCALE: Locale = "en";

/** The shape every bundle mirrors — `en.json` is the reference copy. */
export type Bundle = typeof en;

/** Gate families are looked up by a key the server chooses, so they need a real list. */
export const FAMILY_KEYS = Object.keys(en.families) as Array<keyof Bundle["families"]>;
