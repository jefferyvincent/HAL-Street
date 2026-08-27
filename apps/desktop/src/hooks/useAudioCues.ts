import { useEffect, useRef } from "react";
import { CUE_GAP_MS } from "@/constants/theme";
import { type Watched, decide, watch } from "@/lib/cues";
import { CUES, ready, unlock } from "@/lib/sounds";
import { useUI } from "@/stores/ui";
import type { Snapshot } from "@/types";

/**
 * Sounds the desk's cues off the snapshot: the bell at each end of the session, a
 * till for a closed winner, a buzzer for a closed loser.
 *
 * The whole difficulty is *when*, not what. The snapshot is a complete picture of
 * the world, pushed every time anything changes, so the naive version rings the
 * till once for every historical winner the moment you open the panel — and then
 * again on every reconnect. Two rules avoid that:
 *
 *   1. The first snapshot only records what is already there. It never sounds.
 *      Opening a dashboard is not an event; it is the absence of one.
 *   2. Everything after fires only on what is genuinely new, keyed by
 *      `structure_id` for trades and by transition for the bell. The server marks
 *      the session it merely *found* on startup with `observed`, so a scheduler
 *      that began mid-session does not get an opening bell it never heard.
 *
 * Muting is honoured here rather than in the sound functions, so a muted panel does
 * not silently accumulate a backlog: it still records what it saw, and un-muting
 * starts from the present rather than replaying the morning.
 */
export function useAudioCues(snapshot: Snapshot | null) {
  const muted = useUI((s) => s.muted);
  const watched = useRef<Watched>(watch());
  // Read through a ref so a mute toggled *between* a snapshot and a staggered sound
  // is honoured, and so the effect does not re-run on it — re-running would replay
  // the decision against an already-advanced watch list.
  const mutedNow = useRef(muted);
  mutedNow.current = muted;

  useEffect(() => {
    if (!snapshot) return;
    // Always decided, even while muted, so the watch list stays current: un-muting
    // starts from the present rather than replaying the morning.
    const cues = decide(watched.current, snapshot.closed ?? [], snapshot.market ?? null);
    if (mutedNow.current || !ready() || cues.length === 0) return;

    cues.forEach((cue, i) => {
      // Staggered, so three exits in one cycle are three sounds rather than a chord.
      window.setTimeout(() => {
        if (!mutedNow.current) CUES[cue]();
      }, i * CUE_GAP_MS);
    });
  }, [snapshot]);
}


/**
 * Turning sound on, which a browser will only allow from a real gesture.
 *
 * Returned as a handler rather than run on mount: an AudioContext created outside a
 * gesture starts suspended and stays that way, so the toggle would read as enabled
 * and produce nothing at all.
 */
/**
 * Arms the audio context on the first real gesture anywhere in the page.
 *
 * Sound is on by default now, and a preference the browser will not honour is worse
 * than one that is off: the toggle reads "SOUND", nothing plays, and there is no way
 * to tell a suspended context from a quiet market. A one-shot listener on the
 * document turns the first click, key or touch — whatever it was for — into the
 * gesture the AudioContext needs.
 *
 * `once` on all three and a removal on unmount, so this costs one listener that
 * deletes itself. It does nothing while muted: arming audio for someone who asked
 * for silence is the wrong side of the same mistake.
 */
export function useAudioUnlock(): void {
  useEffect(() => {
    if (ready()) return;
    const arm = () => {
      if (!useUI.getState().muted) void unlock();
    };
    const events: (keyof DocumentEventMap)[] = ["pointerdown", "keydown", "touchstart"];
    for (const name of events) document.addEventListener(name, arm, { once: true });
    return () => {
      for (const name of events) document.removeEventListener(name, arm);
    };
  }, []);
}


export function useSoundToggle() {
  const muted = useUI((s) => s.muted);
  const setMuted = useUI((s) => s.setMuted);
  return {
    muted,
    toggle: async () => {
      if (muted) await unlock();
      setMuted(!muted);
    },
  };
}
