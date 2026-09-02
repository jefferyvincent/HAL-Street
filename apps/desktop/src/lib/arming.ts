/**
 * What to do with a gesture that could start the audio context.
 *
 * The listener used to be registered `{ once: true }`, which is one attempt and no
 * second one. Any gesture that failed to start the context — the panel was muted at
 * that moment, the resume did not take, the click landed during hydration — spent the
 * only attempt there was, and the control then read ARMING for the rest of the session
 * with muting and un-muting as the sole recovery.
 *
 * Three outcomes, and the middle one is the whole point: a muted panel is not a failed
 * arming, so the gesture is skipped and the listener stays. Pure and here rather than
 * in the hook because "what does this gesture mean" is a rule, and a rule inside a
 * document listener is one no test can reach without a DOM.
 */
export type ArmingStep = "stop" | "try" | "skip";

export function armingStep(state: { muted: boolean; ready: boolean }): ArmingStep {
  if (state.ready) return "stop";
  return state.muted ? "skip" : "try";
}
