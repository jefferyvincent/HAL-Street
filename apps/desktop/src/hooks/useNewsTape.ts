import { useMemo } from "react";

import { newsChips } from "@/lib/newsChips";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

export interface Headline {
  key: string;
  /** Empty unless the server's scheme allowlist passed it. Never re-checked here. */
  url: string;
  title: string;
  headline: string;
  source: string;
  /** The symbols to draw as chips — our reads if any, else the publisher's tags. */
  chips: string[];
  /** True when a catalyst read it; false when the census merely saw it go past. */
  read: boolean;
  /** "3h", or null where the publisher gave no time. */
  age: string | null;
}

/**
 * What the agent is watching, doubled so the strip scrolls without a seam.
 *
 * Two sources: the headlines a catalyst read for a symbol it was scanning, and the
 * market-wide census discovery ranks the universe from. The second is most of the
 * strip now — a per-symbol feed can only carry news about names already being
 * scanned, which is why a pinned universe scrolled the same handful of stories.
 *
 * The track translates by exactly half its width, at which point the copy sits where
 * the original started. A single pass would leave the strip empty for as long as it
 * took to come round.
 *
 * **Untrusted text, carried as data.** These are publisher strings; nothing here
 * parses, links or interprets them, and React escapes the lot at the other end.
 */
export function useNewsTape(): Headline[] {
  const t = useStrings();
  const headlines = useConnection((s) => s.snapshot?.headlines) ?? [];

  return useMemo(() => {
    const items = headlines.map((h, i) => ({
      key: `${h.headline}-${i}`,
      url: h.url,
      // Two claims, and only one of them is true of any given article. The strip
      // used to say "the catalyst read this" of everything on it, which stopped
      // being true the moment the census started feeding it.
      title: h.read
        ? t.news.wasRead(h.roots.join(t.common.listSep), h.source)
        : t.news.fromCensus(h.source),
      headline: h.headline,
      source: h.source,
      chips: newsChips(h.roots, h.symbols),
      read: h.read,
      age: h.age_hours === null ? null : t.news.age(Math.round(h.age_hours)),
    }));
    // Doubled end to end. Keys are suffixed per pass so the two copies never collide.
    return [
      ...items,
      ...items.map((item) => ({ ...item, key: `${item.key}-repeat` })),
    ];
  }, [headlines, t]);
}
