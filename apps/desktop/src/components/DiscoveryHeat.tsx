import { cn } from "@/lib/cn";
import { CLS } from "@/constants/theme";
import { useDiscoveryHeat } from "@/hooks/useDiscoveryHeat";
import { useStrings } from "@/hooks/useStrings";

/**
 * Every symbol the news feed named this pass, brightest where it was named most.
 *
 * The map exists because the shortlist on its own is a list. Six names tell you what
 * the agent scanned; sixty tell you what it chose *between*, and where the cut fell
 * across the morning. What each tile means is decided in `useDiscoveryHeat` and
 * `lib/heat` — this file lays them out.
 */
export function DiscoveryHeat() {
  const t = useStrings();
  const { tiles, legend, meta, scanned, hottest, empty } = useDiscoveryHeat();

  return (
    <>
      <div className={CLS.heading}>
        {t.discovery.title}
        <span className="flex-1" />
        <span className={CLS.headingMeta}>
          {meta}{t.common.sep}{scanned}{t.common.sep}{hottest}
        </span>
      </div>

      {empty ? (
        <div className={cn(CLS.empty, "border border-line bg-panel")}>{empty}</div>
      ) : (
        <>
          <div className="flex flex-wrap gap-[5px] border border-line bg-panel p-3">
            {tiles.map((tile) => (
              <span
                key={tile.key}
                title={tile.title}
                style={tile.style}
                className={cn(
                  "flex min-w-[62px] flex-col items-center gap-[3px] rounded-[3px]",
                  "border px-[7px] py-[6px] font-mono leading-none transition-colors",
                )}
              >
                <span className={cn("text-[10.5px] font-bold tracking-[.04em]",
                  tile.refused && "line-through decoration-1")}>
                  {tile.symbol}
                </span>
                <span className="text-[9px] tabular-nums opacity-70">{tile.count}</span>
              </span>
            ))}
          </div>

          <div className="mt-2 flex flex-wrap items-start gap-x-5 gap-y-2 border border-line bg-panel px-3 py-[10px]">
            <span className="font-mono text-[8.5px] font-bold leading-none tracking-[.12em] text-ink/40">
              {t.discovery.legend}
            </span>
            {legend.map((key) => (
              <span key={key.key} className="flex items-baseline gap-[7px]">
                <span style={key.style}
                      className="inline-block h-[10px] w-[10px] shrink-0 translate-y-[1px] rounded-[2px] border" />
                <span className="font-mono text-[10px] leading-none text-ink/70">
                  {key.label}
                </span>
                <span className="max-w-[280px] font-sans text-[10.5px] leading-[1.4] text-ink/35">
                  {key.note}
                </span>
              </span>
            ))}
          </div>
        </>
      )}

      <p className="mt-2 font-sans text-[11px] leading-[1.5] text-ink/35">
        {t.discovery.note}
      </p>
    </>
  );
}
