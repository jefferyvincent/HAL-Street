/**
 * What the console counts down to, and how long is left.
 *
 * A panel that says nothing about *when* the agent acts next is a panel that cannot be
 * told apart from a stopped one — which is the thread running through most of this
 * screen's history. The bell already says which side of the session we are on; this
 * says how long until the next thing happens.
 *
 * Three targets, in the order they answer the question a reader actually has:
 *
 *   open   — the market is shut. Nothing will happen until it opens, and that time is
 *            the broker's own published figure.
 *   scan   — the market is open and the cadence is known. This is the useful one.
 *   close  — the market is open but the next scan cannot be projected, either because
 *            nothing has scanned yet or because the projection has already lapsed.
 *
 * A projected scan that is already in the past is not shown. It has stopped being a
 * projection of anything, and a timer reading DUE for the rest of an afternoon says
 * something is imminent when the agent has in fact stopped — which the console says
 * plainly elsewhere and should not contradict here.
 *
 * No words here, by rule.
 */

export type Target = "open" | "scan" | "close";

export interface Countdown {
  target: Target;
  /** Seconds remaining, never negative. */
  seconds: number;
}

export interface CountdownInput {
  marketState: string | null;
  nextOpen: string | null;
  nextClose: string | null;
  /** When the scan in progress (or the last one) began. */
  lastScanAt: string | null;
  /** The scheduler's cadence, or null where it is not known. */
  intervalS: number | null;
  now: number;
}

/** How long until the next thing happens, and what that thing is. */
export function countdown(input: CountdownInput): Countdown | null {
  const ahead = (ts: string | null): number | null => {
    if (!ts) return null;
    const at = new Date(ts).getTime();
    if (Number.isNaN(at)) return null;
    const left = Math.round((at - input.now) / 1000);
    return left > 0 ? left : null;
  };

  if (input.marketState === "closed") {
    const left = ahead(input.nextOpen);
    return left === null ? null : { target: "open", seconds: left };
  }

  if (input.marketState === "open") {
    if (input.lastScanAt && input.intervalS && input.intervalS > 0) {
      const began = new Date(input.lastScanAt).getTime();
      if (!Number.isNaN(began)) {
        const due = began + input.intervalS * 1000;
        const left = Math.round((due - input.now) / 1000);
        if (left > 0) return { target: "scan", seconds: left };
      }
    }
    const left = ahead(input.nextClose);
    return left === null ? null : { target: "close", seconds: left };
  }

  // Nothing has recorded which side of the bell we are on. Counting down to anything
  // would be inventing the one fact the panel does not have.
  return null;
}

/**
 * `12:43`, or `1:04:22` once there is an hour in it.
 *
 * Minutes and seconds are always two digits so the figure never changes width — this
 * ticks once a second beside a number people read at a glance, and a column that
 * jitters is one you stop trusting to be still.
 */
export function clockOf(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
}
