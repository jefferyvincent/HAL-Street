/**
 * What the sound control says it is doing.
 *
 * Three states and they are genuinely three: silenced by choice, wanting to play but
 * not yet permitted by the browser, and playing. A control that says it is on while
 * nothing can come out is the one failure worth avoiding here — that is why ARMING
 * exists at all.
 *
 * Pure, and here rather than in the component, because "which of three states is
 * this" is a rule. It was previously decided inline from `sounds.ready()`, which
 * reads the AudioContext directly: module state React has no reason to re-render on,
 * so the label stuck at ARMING long after the context had started.
 */
export interface SoundWords {
  off: string;
  on: string;
  arming: string;
}

export function soundLabel(state: { muted: boolean; armed: boolean },
                           words: SoundWords): string {
  if (state.muted) return words.off;
  return state.armed ? words.on : words.arming;
}
