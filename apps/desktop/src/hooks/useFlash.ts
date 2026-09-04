import { useEffect, useRef, useState } from "react";

import { flashOf, type Flash } from "@/lib/flash";
import { FLASH_MS } from "@/constants/theme";

/**
 * A figure's direction for the moment after it moves, then nothing.
 *
 * The decision is `lib/flash.flashOf`, where the three cases that must stay dark are
 * seven assertions from a test. This holds the previous value and clears the mark
 * after a beat, which is the part that needs React.
 *
 * The timer is cleared on every change and on unmount: two moves inside the window
 * would otherwise leave the first one's timeout to switch the second one off early.
 */
export function useFlash(value: number | null): Flash {
  const previous = useRef<number | null>(null);
  const [flash, setFlash] = useState<Flash>("");

  useEffect(() => {
    const direction = flashOf(previous.current, value);
    previous.current = value;
    if (!direction) return;

    setFlash(direction);
    const timer = window.setTimeout(() => setFlash(""), FLASH_MS);
    return () => window.clearTimeout(timer);
  }, [value]);

  return flash;
}
