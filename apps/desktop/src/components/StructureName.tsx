import { cn } from "@/lib/cn";
import { useStructureName } from "@/hooks/useStructureName";

/**
 * A structure's name, with the strategy coloured away from the numbers.
 *
 * `2026-10-16 765/775 ` then **call credit spread** in its own colour. The strategy is
 * the part a trader scans a book for and it had the least contrast on the row: eleven
 * characters of prose at the end of a line of digits, rendered exactly like the
 * digits.
 *
 * One component rather than the same split repeated in five views, because the views
 * disagree about what precedes the name — the console strips the ticker, the tape
 * does not — and a shared parser each of them re-implements is one that drifts.
 */
export function StructureName({ name, root, className }: {
  name: string;
  /** Stripped from the front when present, so the ticker is never printed twice. */
  root?: string;
  className?: string;
}) {
  const { head, strategy, strategyClass } = useStructureName(name, root);

  return (
    <span className={cn("min-w-0", className)}>
      {head}
      {strategy && (
        <>
          {" "}
          <span className={cn("font-semibold", strategyClass)}>{strategy}</span>
        </>
      )}
    </span>
  );
}
