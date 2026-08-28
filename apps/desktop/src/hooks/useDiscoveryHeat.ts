import { useMemo } from "react";

import { heatCells, heatStyle, type HeatCell } from "@/lib/heat";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

export interface HeatTile {
  key: string;
  symbol: string;
  count: string;
  /** The whole story on hover: how loud, what came of it, and the headline behind it. */
  title: string;
  style: React.CSSProperties;
  refused: boolean;
}

export interface LegendKey {
  key: string;
  label: string;
  note: string;
  style: React.CSSProperties;
}

export interface HeatMap {
  tiles: HeatTile[];
  legend: LegendKey[];
  meta: string;
  scanned: string;
  hottest: string;
  /** The words for an empty map, or null when there is one to draw. */
  empty: string | null;
}

/**
 * The census as a heat map: every symbol the tape named, brightest where it named most.
 *
 * Two channels, kept apart deliberately — see `lib/heat`. Brightness is mention count,
 * which is a fact about the feed. The border is what the agent did, which is a fact
 * about the agent. A name below the cut is drawn at its real heat with no verdict
 * colour, because none was reached; dimming it would have the map claim the tape was
 * quiet about a name it was not.
 *
 * The empty state distinguishes "nothing has scanned yet" from "this run pins its
 * universe, so there will never be a census" — the second is a configuration, not a
 * wait, and a panel that says "no data" to both leaves someone watching for a map that
 * is never coming.
 */
export function useDiscoveryHeat(): HeatMap {
  const t = useStrings();
  const discovery = useConnection((s) => s.snapshot?.discovery);
  const armed = useConnection((s) => s.snapshot?.armed);

  return useMemo(() => {
    const cells: HeatCell[] = heatCells(discovery?.cells ?? [], discovery?.hottest ?? 1);
    const scanned = cells.filter((c) => c.status === "scanned").length;

    return {
      tiles: cells.map((c) => ({
        key: c.symbol,
        symbol: c.symbol,
        count: t.discovery.mentions(c.mentions),
        title: c.reason
          ? t.discovery.cellRefused(c.symbol, c.mentions, c.reason, c.headline)
          : t.discovery.cellTitle(c.symbol, c.mentions, c.headline),
        style: heatStyle(c.level, c.status),
        refused: c.status === "refused",
      })),
      legend: [
        { key: "scanned", label: t.discovery.scanned, note: t.discovery.scannedNote,
          style: heatStyle(1, "scanned") },
        { key: "refused", label: t.discovery.refused, note: t.discovery.refusedNote,
          style: heatStyle(1, "refused") },
        { key: "not-reached", label: t.discovery.notReached,
          note: t.discovery.notReachedNote, style: heatStyle(1, "not-reached") },
      ],
      meta: t.discovery.meta(discovery?.symbols ?? 0, discovery?.headlines ?? 0),
      scanned: t.discovery.cut(scanned),
      hottest: t.discovery.hottest(discovery?.hottest ?? 0),
      // Two different silences. No snapshot at all is a panel still connecting, and
      // saying anything about the universe there would be a guess. A snapshot that
      // has scanned and holds no census means this run pins its universe — which is
      // a configuration, not a wait, and someone told "no data" would sit watching
      // for a map that is never coming.
      empty: cells.length
        ? null
        : armed === undefined ? t.discovery.emptyWaiting : t.discovery.emptyNoCensus,
    };
  }, [discovery, armed, t]);
}
