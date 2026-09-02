/**
 * What the sound control says it is doing.
 *
 * Two states, and it used to be three. ARMING meant "sound is wanted and the browser
 * has not granted the audio context yet", which is a real thing to be and was worth
 * saying — a control claiming to be on while nothing can come out is the failure it
 * existed to prevent.
 *
 * It went wrong twice in the same way. The label depended on a readiness flag that
 * could disagree with the actual AudioContext: first because readiness was module
 * state React had no reason to re-render on, then because a single failed unlock
 * attempt left the flag false forever. Each time, the control sat there describing a
 * state the app had already left, which is its own kind of lying.
 *
 * So the state it could get wrong is gone. Arming still happens — `useAudioUnlock`
 * listens for the gesture the browser requires — it is simply no longer narrated. The
 * gap it covered is the moment between opening the panel and the first click, and a
 * trading console mislabelling its mute button for that long is a smaller cost than a
 * label that is wrong all afternoon.
 */
export interface SoundWords {
  off: string;
  on: string;
}

export function soundLabel(state: { muted: boolean }, words: SoundWords): string {
  return state.muted ? words.off : words.on;
}
