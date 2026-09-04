import { useEffect, useState } from "react";

/** How often the desk's own clock advances. Quarter-second, as HAL's does. */
const TICK_MS = 250;

/**
 * A clock that moves, but only while something is using it.
 *
 * The snapshot arrives when the journal changes and a stage writes nothing for twenty
 * seconds at a time, so every elapsed figure on the panel was frozen between pushes.
 *
 * Gated on `running` rather than always on. An idle console re-rendering four times a
 * second for a number nobody is reading is a laptop fan, and this panel is meant to be
 * left open all day.
 */
export function useTick(running: boolean, ms: number = TICK_MS): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!running) return;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), ms);
    return () => window.clearInterval(id);
  }, [running, ms]);

  return now;
}
