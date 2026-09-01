import { cn } from "@/lib/cn";
import { CLS } from "@/constants/theme";
import { usePayoff } from "@/hooks/usePayoff";
import { useStrings } from "@/hooks/useStrings";
import type { StructureChart as Chart } from "@/types";

/**
 * What this position can do at expiry, against what the underlying does.
 *
 * The chart above it draws what the structure has been worth; this draws what it can
 * be worth, which is the shape the strikes were chosen to make. Everything it says is
 * worked out in `usePayoff` — this is the frame.
 *
 * Drawn as one SVG rather than a second lightweight-charts instance: the curve is four
 * or five straight segments with a kink at each strike, and a charting library would
 * bring an axis, a crosshair and a resize observer to draw a line that has no detail
 * to lose.
 */
export function PayoffChart({ chart }: { chart: Chart }) {
  const t = useStrings();
  const { shape, tiles, box, empty, spotLabel, strikeLabels } = usePayoff(chart);

  return (
    <div className="mt-3">
      <div className="mb-2 flex items-baseline gap-2">
        <span className="font-mono text-[10px] font-bold leading-none tracking-[.12em] text-ink/60">
          {t.payoff.title}
        </span>
        {spotLabel && (
          <span className="font-mono text-[9.5px] leading-none text-amber/80">{spotLabel}</span>
        )}
      </div>

      {shape ? (
        <>
          <div className="grid grid-cols-3 gap-px bg-line">
            {tiles.map((tile) => (
              <div key={tile.label} className="bg-void px-[10px] py-[9px]">
                <div className="font-mono text-[8.5px] font-bold leading-none tracking-[.08em] text-ink/40">
                  {tile.label}
                </div>
                <div className={cn("mt-[5px] font-mono text-[13px] font-semibold leading-none tabular-nums",
                  tile.tone)}>
                  {tile.value}
                </div>
              </div>
            ))}
          </div>

          <svg viewBox={`0 0 ${box.w} ${box.h}`} preserveAspectRatio="none"
               role="img" aria-label={t.payoff.title}
               className="mt-px h-[150px] w-full border border-line bg-panel">
            {/* Break-even. The one line on the picture that is not a price. */}
            <line x1={0} y1={shape.zeroY} x2={box.w} y2={shape.zeroY}
                  className="stroke-line" strokeWidth={1} vectorEffect="non-scaling-stroke" />

            {shape.strikes.map((s) => (
              <line key={s.strike} x1={s.x} y1={0} x2={s.x} y2={box.h}
                    className="stroke-line/60" strokeWidth={1} strokeDasharray="2 3"
                    vectorEffect="non-scaling-stroke" />
            ))}

            {shape.gainArea && (
              <path d={shape.gainArea} className="fill-pass/15" />
            )}
            {shape.lossArea && (
              <path d={shape.lossArea} className="fill-fail/15" />
            )}

            <path d={shape.line} fill="none" className="stroke-ink" strokeWidth={1.5}
                  strokeLinejoin="round" vectorEffect="non-scaling-stroke" />

            {shape.breakevens.map((b) => (
              <circle key={b.price} cx={b.x} cy={shape.zeroY} r={3}
                      className="fill-panel stroke-ink" strokeWidth={1.5}
                      vectorEffect="non-scaling-stroke" />
            ))}

            {shape.spotX !== null && (
              <line x1={shape.spotX} y1={0} x2={shape.spotX} y2={box.h}
                    className="stroke-amber" strokeWidth={1.5}
                    vectorEffect="non-scaling-stroke" />
            )}
          </svg>

          <div className="relative h-[13px]">
            {strikeLabels.map((s) => (
              <span key={s.key}
                    style={{ left: s.leftPct }}
                    className="absolute -translate-x-1/2 font-mono text-[8.5px] leading-none text-ink/40 tabular-nums">
                {s.label}
              </span>
            ))}
          </div>
        </>
      ) : (
        <div className={cn(CLS.empty, "border border-line bg-panel")}>{empty}</div>
      )}

      <div className="mt-2 font-mono text-[9.5px] leading-[1.4] text-ink/35">{t.payoff.note}</div>
    </div>
  );
}
