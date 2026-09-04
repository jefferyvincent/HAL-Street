import { ICON } from "@/constants/icons";
import { STROKE } from "@/constants/theme";
import { Icon } from "@/components/Icon";
import { useTrend } from "@/hooks/useTrend";

/**
 * Up or down beside a figure whose sign is the whole point.
 *
 * Colour alone carries this today, and colour alone is the one encoding some
 * readers do not get — red and green are the commonest pair to lose, and this
 * panel uses exactly that pair for won and lost. A shape says the same thing
 * without depending on hue, and costs ten pixels.
 *
 * Nothing for zero, which `useTrend` decides: a scratch is neither.
 */
export function Trend({ value, size = 9 }: { value: number | string | null; size?: number }) {
  const direction = useTrend(value);
  if (!direction) return null;

  const up = direction === "up";
  return (
    <Icon
      d={up ? ICON.up : ICON.down}
      size={size}
      stroke={up ? STROKE.pass : STROKE.fail}
      width={0}
      className={up ? "fill-pass" : "fill-fail"}
    />
  );
}
