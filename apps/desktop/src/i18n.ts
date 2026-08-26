/**
 * i18next, wired once at startup.
 *
 * Every bundle in `locales/` is registered under the default `translation`
 * namespace; the panel is small enough that splitting namespaces would only add
 * a prefix to every key. Interpolation escaping is off because React escapes what
 * it renders — leaving it on would double-encode the em dashes and middots the
 * panel is full of.
 */

import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import { DEFAULT_LOCALE, LOCALES } from "@/locales";

const resources = Object.fromEntries(
  Object.entries(LOCALES).map(([locale, translation]) => [locale, { translation }]),
);

void i18n.use(initReactI18next).init({
  resources,
  lng: DEFAULT_LOCALE,
  fallbackLng: DEFAULT_LOCALE,
  interpolation: { escapeValue: false },
});

export default i18n;
