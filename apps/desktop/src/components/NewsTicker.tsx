import { useMemo } from "react";
import { cn } from "@/lib/cn";
import { Ticker } from "@/components/Ticker";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

/**
 * What the agent has been reading, scrolling under the chrome.
 *
 * The news is the one input to a cycle that does not come from arithmetic. Everything
 * else on this screen is a number the desk computed; this is the part that came from
 * outside, and until now the panel said only how many there were.
 *
 * A strip below the tab bar rather than inside it: the chrome row is already six
 * status chips wide and wraps at narrow widths, and a marquee competing with the
 * navigation for space would win the wrong fight.
 *
 * **Untrusted text, rendered as text.** These are publisher strings. They reach the
 * catalyst inside an explicit fence and they arrive here as data — nothing is parsed,
 * nothing is linked, no markup is interpreted, and React escapes the lot. A headline
 * is the last thing in this system that should be able to say anything to it.
 */
export function NewsTicker() {
  const t = useStrings();
  const headlines = useConnection((s) => s.snapshot?.headlines) ?? [];

  // Duplicated end to end so the scroll wraps without a seam: the track translates by
  // exactly half its width, at which point the copy sits where the original started.
  // A single pass would leave the strip empty for as long as it took to come round.
  const track = useMemo(() => [...headlines, ...headlines], [headlines]);

  if (headlines.length === 0) return null;

  return (
    <div className="group relative flex items-center overflow-hidden border-b border-line bg-sunk"
         title={t.news.title}>
      {/* Fixed, and above the scroll: a moving strip with no label is a mystery, and
          this one is the difference between "the market did this" and "the desk read
          this". */}
      <span className="z-10 shrink-0 border-r border-line bg-sunk px-3 py-[6px] font-mono text-[9px] font-bold leading-none tracking-[.14em] text-ink/40">
        {t.news.label}
      </span>

      <div className="relative min-w-0 flex-1 overflow-hidden py-[6px]">
        <div className="ticker-track flex w-max items-center gap-[26px] group-hover:[animation-play-state:paused]">
          {track.map((h, i) => (
            <Item key={`${h.headline}-${i}`} url={h.url} title={t.news.read(h.source)}>
              {/* Which of the three reads picked it up. A macro story tagged with all
                  of them is a different kind of story from one about a single name,
                  and that is visible here before the words are. */}
              {h.roots.map((root) => <Ticker key={root} symbol={root} />)}
              <span className={cn("text-ink/70", h.url && "group-hover/item:text-ink group-hover/item:underline")}>
                {h.headline}
              </span>
              <span className="font-mono text-[9.5px] text-ink/30">{h.source}</span>
              {h.age_hours !== null && (
                <span className="font-mono text-[9.5px] tabular-nums text-ink/25">
                  {t.news.age(Math.round(h.age_hours))}
                </span>
              )}
            </Item>
          ))}
        </div>
        {/* The right edge only. The left is where the label sits, and fading into a
            solid block would look like a rendering fault rather than a fade. */}
        <div className={cn("pointer-events-none absolute inset-y-0 right-0 w-10",
          "bg-gradient-to-l from-sunk to-transparent")} />
      </div>
    </div>
  );
}

/**
 * One headline: a link to the publisher when there is a safe one, plain text when not.
 *
 * We link out rather than reproducing the article. The body is the publisher's, and a
 * headline plus a way to the source is both the honest presentation and the useful
 * one — it also means nothing of theirs is ever rendered by this page.
 *
 * `url` is empty unless it passed the server's scheme allowlist. That check is not
 * repeated here on purpose: it is a security control, and a control implemented in
 * two places is one implemented in whichever place someone forgets. `safe_url` in
 * `marketdata/news.py` is the single place, and it has the tests.
 *
 * `noopener` and `noreferrer` regardless — the opened page gets no handle back to
 * this one, which matters more than usual for a page showing a live trading account.
 */
function Item({ url, title, children }: {
  url: string; title: string; children: React.ReactNode;
}) {
  const inner = "flex shrink-0 items-baseline gap-[7px] font-sans text-[11px] leading-none";
  if (!url) return <span className={inner}>{children}</span>;
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" title={title}
       className={cn(inner, "group/item cursor-pointer",
         "focus-visible:outline focus-visible:outline-1 focus-visible:outline-amber")}>
      {children}
    </a>
  );
}
