import { ICON } from "@/constants/icons";
import { STROKE } from "@/constants/theme";
import { Icon } from "@/components/Icon";

/**
 * Up or down beside a figure whose sign is the whole point.
 *
 * Colour alone carries this today, and colour alone is the one encoding some
 * readers do not get — red and green are the commonest pair to lose, and this
 * panel uses exactly that pair for won and lost. A shape says the same thing
 * without depending on hue, and costs ten pixels.
 *
 * Nothing for zero. A scratch is neither, and an arrow pointing somewhere would be
 * asserting a direction the number does not have.
 */
export function Trend({ value, size = 9 }: { value: number | string | null; size?: number }) {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return null;
  const up = n > 0;
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
