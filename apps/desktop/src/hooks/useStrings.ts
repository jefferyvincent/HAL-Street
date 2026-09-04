import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { makeStrings, type Strings, type Translate } from "@/constants/strings";

/**
 * The active string table.
 *
 * `useTranslation` subscribes the component to i18next, so switching language
 * re-renders every consumer; the table is rebuilt only when the language actually
 * changes, which keeps the identity stable for the `useMemo`s downstream that take
 * it as a dependency.
 */
export function useStrings(): Strings {
  const { t, i18n } = useTranslation();
  const translate = t as unknown as Translate;
  return useMemo(() => makeStrings(translate), [translate, i18n.language]);
}
