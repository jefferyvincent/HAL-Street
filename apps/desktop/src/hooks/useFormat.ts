import { useMemo } from "react";

import { makeFormat, type Format } from "@/lib/format";
import { useStrings } from "@/hooks/useStrings";

/**
 * The number formatters, in the active language.
 *
 * `lib/format.ts` holds the arithmetic of display and none of the words; this is
 * where the two meet. Rebuilt only when the string table is, so the identity is
 * stable for the `useMemo`s that take it as a dependency.
 */
export function useFormat(): Format {
  const t = useStrings();
  return useMemo(() => makeFormat(t.format), [t]);
}
