import { ICON } from "@/constants/icons";
import { STROKE } from "@/constants/theme";

/** One stroke icon. `d` may hold several subpaths, separated by " M". */
export function Icon({ d, size = 13, stroke = "currentColor", width = 2 }: {
  d: string;
  size?: number;
  stroke?: string;
  width?: number;
}) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth={width}>
      {d.split(" M").map((seg, i) => (
        <path key={i} d={i === 0 ? seg : "M" + seg} />
      ))}
    </svg>
  );
}

export const Tick = ({ size = 12 }: { size?: number }) => (
  <Icon d={ICON.tick} size={size} stroke={STROKE.pass} width={3} />
);

export const Cross = ({ size = 12 }: { size?: number }) => (
  <Icon d={ICON.cross} size={size} stroke={STROKE.fail} width={2.8} />
);

/** The footnote that appears under each view, with the shield glyph. */
export function Note({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-3 flex gap-[9px] border border-line bg-void px-3 py-[10px] font-sans text-[11.5px] leading-[1.5] text-ink/40">
      <Icon d={ICON.shield} stroke={STROKE.muted} width={2.2} />
      <span>{children}</span>
    </div>
  );
}
