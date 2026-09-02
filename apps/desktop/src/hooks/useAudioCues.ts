import { useEffect, useRef } from "react";
import { CUE_GAP_MS } from "@/constants/theme";
import { type Watched, decide, watch } from "@/lib/cues";
import { CUES, ready, unlock } from "@/lib/sounds";
import { armingStep } from "@/lib/arming";
import { soundLabel } from "@/lib/soundLabel";
import { useStrings } from "@/hooks/useStrings";
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
 * It listens until it succeeds, and then removes itself. `once: true` was the first
 * version and it is one attempt with no second: a gesture that arrived while the panel
 * was muted, or a resume that did not take, spent the only attempt there was and the
 * control read ARMING for the rest of the session. It still arms nothing while muted —
 * audio for someone who asked for silence is the wrong side of the same mistake — but
 * it keeps listening rather than treating that as its one go.
 */
export function useAudioUnlock(): void {
  useEffect(() => {
    if (ready()) return;
    const events: (keyof DocumentEventMap)[] = ["pointerdown", "keydown", "touchstart"];
    const stop = () => {
      for (const name of events) document.removeEventListener(name, arm);
    };
    const arm = () => {
      const step = armingStep({ muted: useUI.getState().muted, ready: ready() });
      if (step === "stop") return stop();
      if (step === "skip") return;          // muted: stay listening, arm nothing
      void armAudio().then(() => {
        if (ready()) stop();
      });
    };
    for (const name of events) document.addEventListener(name, arm);
    return stop;
  }, []);
}


/**
 * Unlock the context and record whether it actually started.
 *
 * Both callers go through here so the store cannot fall out of step with the
 * AudioContext — which is the whole bug: readiness lived only in the module, and the
 * label that depended on it never re-rendered.
 */
async function armAudio(): Promise<void> {
  await unlock();
  useUI.getState().setArmed(ready());
}


export function useSoundToggle() {
  const t = useStrings();
  const muted = useUI((s) => s.muted);
  const armed = useUI((s) => s.armed);
  const setMuted = useUI((s) => s.setMuted);
  return {
    muted,
    armed,
    // Decided here, not in the markup: which of three states this is, is a rule.
    label: soundLabel({ muted }, {
      off: t.chrome.soundOff, on: t.chrome.soundOn,
    }),
    toggle: async () => {
      if (muted) await armAudio();
      setMuted(!muted);
    },
  };
}
