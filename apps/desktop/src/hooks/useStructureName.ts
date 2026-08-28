import { useMemo } from "react";

import { structureName, type StructureNameParts } from "@/lib/strategy";

/**
 * A structure's name, split into the numbers and the strategy, with the class to
 * paint the strategy in.
 *
 * Thin on purpose. The decision is `lib/strategy.structureName`, where it is five
 * assertions away from a test; this only holds it still between renders so the
 * component's identity does not churn.
 */
export function useStructureName(name: string, root?: string): StructureNameParts {
  return useMemo(() => structureName(name, root), [name, root]);
}
