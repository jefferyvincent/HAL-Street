import { useMemo } from "react";

import { payoffCurve } from "@/lib/payoff";
import { payoffShape } from "@/lib/payoffShape";
import { useFormat } from "@/hooks/useFormat";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";
import type { StructureChart as Chart } from "@/types";

/**
 * The box the curve is drawn in. Fixed, and scaled by the viewBox rather than
 * measured from the DOM: the shape is piecewise linear, so it carries no detail that
 * a resize could crowd, and measuring would put a ResizeObserver on a picture that
 * does not need one.
 */
const W = 640;
const H = 150;

export interface PayoffTile {
  label: string;
  value: string;
  tone: string;
}

/**
 * What this position can do at expiry, ready to draw.
 *
 * Three states, named rather than merged: a curve, no entry price, or a leg whose
 * symbol cannot be read. The last two are both "no chart" and they are not the same
 * fact — one is a gap in the ledger and the other is a contract shaped unlike any the
 * agent trades — so the panel says which rather than showing one empty box for both.
 *
 * Spot comes from the last scan's own reading for this underlying. It is a marker, not
 * a measurement the curve depends on: absent, the picture is unchanged and simply has
 * no "you are here". A price from a different name would be worse than none, so the
 * match is on the underlying and nothing else.
 */
export function usePayoff(chart: Chart) {
  const t = useStrings();
  const f = useFormat();
  const rows = useConnection((c) => c.snapshot?.pass?.rows);

  const spot = useMemo(() => {
    const row = (rows ?? []).find((r) => r.underlying === chart.underlying);
    const value = row?.spot === undefined || row?.spot === null ? null : Number(row.spot);
    return value !== null && Number.isFinite(value) ? value : null;
  }, [rows, chart.underlying]);

  const entry = chart.levels ? Number(chart.levels.entry) : null;

  const curve = useMemo(
    () => payoffCurve(chart.legs.map((l) => ({ symbol: l.symbol, contracts: l.contracts })),
                      entry !== null && Number.isFinite(entry) ? entry : null, chart.qty, spot),
    [chart.legs, chart.qty, entry, spot],
  );

  const shape = useMemo(() => payoffShape(curve, W, H, spot), [curve, spot]);

  const tiles: PayoffTile[] = curve
    ? [
        {
          label: t.payoff.maxGain,
          value: curve.maxGain === null ? t.payoff.unbounded : f.money(curve.maxGain),
          tone: "text-pass",
        },
        {
          label: t.payoff.maxLoss,
          value: curve.maxLoss === null ? t.payoff.unbounded : f.money(curve.maxLoss),
          tone: "text-fail",
        },
        {
          label: curve.breakevens.length > 1 ? t.payoff.breakevens : t.payoff.breakeven,
          value: curve.breakevens.length
            ? curve.breakevens.map((b) => f.plain(b, 2)).join(t.common.sep)
            : t.common.dash,
          tone: "text-ink",
        },
      ]
    : [];

  return {
    shape,
    tiles,
    box: { w: W, h: H },
    /** Which of the two silences this is, or null when there is a curve to draw. */
    empty: curve
      ? null
      : entry === null || !Number.isFinite(entry)
        ? t.payoff.noEntry
        : t.payoff.unreadable,
    spotLabel: shape?.spotX !== null && spot !== null ? t.payoff.spot(f.plain(spot, 2)) : null,
    strikeLabels: (shape?.strikes ?? []).map((s) => ({
      key: s.strike,
      // Where the label sits, already in the units the style attribute wants. The
      // component is markup and does no arithmetic on a domain value — including the
      // arithmetic that turns one into a position.
      leftPct: `${(s.x / W) * 100}%`,
      // The strike alone. The root and the expiry are on the header above, and a
      // repeated `SPY261016C00770000` under every bend would bury the four numbers
      // that are the whole point of the picture.
      label: f.plain(s.strike, 2),
    })),
  };
}
