import { useMemo } from "react";

import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

export interface Headline {
  key: string;
  /** Empty unless the server's scheme allowlist passed it. Never re-checked here. */
  url: string;
  title: string;
  headline: string;
  source: string;
  roots: string[];
  /** "3h", or null where the publisher gave no time. */
  age: string | null;
}

/**
 * What the agent has been reading, doubled so the strip scrolls without a seam.
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
      title: t.news.read(h.source),
      headline: h.headline,
      source: h.source,
      roots: h.roots,
      age: h.age_hours === null ? null : t.news.age(Math.round(h.age_hours)),
    }));
    // Doubled end to end. Keys are suffixed per pass so the two copies never collide.
    return [
      ...items,
      ...items.map((item) => ({ ...item, key: `${item.key}-repeat` })),
    ];
  }, [headlines, t]);
}
