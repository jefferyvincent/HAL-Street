/**
 * The desk's four noises, synthesised.
 *
 * No audio files. Not for purity: a bundled .mp3 is a binary blob in a repository
 * that is otherwise entirely readable, it has to be licensed, and the artifact is
 * `dist/` — which the panel serves under a policy that admits nothing external.
 * Four short sounds are about sixty lines of oscillator, and the shape of each one
 * is then legible in the same place as everything else.
 *
 * Every function is a no-op without a live AudioContext, so nothing here can throw
 * into a render. Browsers refuse to start audio before a gesture, which is correct
 * and is why `unlock()` exists rather than an autoplay attempt that fails silently.
 */

let ctx: AudioContext | null = null;

/** Start (or resume) audio. Must be called from a real user gesture. */
export async function unlock(): Promise<boolean> {
  try {
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return false;
    ctx ??= new Ctor();
    if (ctx.state === "suspended") await ctx.resume();
    return ctx.state === "running";
  } catch {
    // A browser with audio disabled entirely. The panel is a trading console
    // first; it must render exactly the same with no sound available.
    return false;
  }
}

export function ready(): boolean {
  return ctx?.state === "running";
}

/**
 * One struck tone. `partials` are multiples of the fundamental — a bell is
 * inharmonic, which is why it reads as metal rather than as a beep, and why the
 * ratios below are not integers.
 */
function strike(
  at: number,
  fundamental: number,
  partials: number[],
  decay: number,
  gain: number,
): void {
  if (!ctx) return;
  for (const [i, ratio] of partials.entries()) {
    const osc = ctx.createOscillator();
    const env = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = fundamental * ratio;
    // Upper partials are quieter and die sooner, which is what a struck object does.
    const level = (gain / (i + 1.6)) * 0.6;
    const life = decay / (1 + i * 0.35);
    env.gain.setValueAtTime(0, at);
    env.gain.linearRampToValueAtTime(level, at + 0.004);
    env.gain.exponentialRampToValueAtTime(0.0001, at + life);
    osc.connect(env).connect(ctx.destination);
    osc.start(at);
    osc.stop(at + life + 0.05);
  }
}

/** Inharmonic ratios measured off a struck bell. Integers would sound like an organ. */
const BELL_PARTIALS = [1, 2.02, 2.99, 4.21, 5.43];

/** Opening bell: two strikes, rising. The session is starting. */
export function openingBell(): void {
  if (!ctx) return;
  const now = ctx.currentTime;
  strike(now, 660, BELL_PARTIALS, 1.9, 0.30);
  strike(now + 0.20, 880, BELL_PARTIALS, 2.6, 0.30);
}

/** Closing bell: three strikes, falling and slowing. Deliberately final. */
export function closingBell(): void {
  if (!ctx) return;
  const now = ctx.currentTime;
  strike(now, 880, BELL_PARTIALS, 1.6, 0.28);
  strike(now + 0.22, 660, BELL_PARTIALS, 2.0, 0.28);
  strike(now + 0.52, 440, BELL_PARTIALS, 3.2, 0.30);
}

/**
 * A till: the mechanical clack of the drawer, then the bright ring over it.
 * The noise burst is what makes it read as a machine rather than a chime.
 */
export function cashRegister(): void {
  if (!ctx) return;
  const now = ctx.currentTime;

  // The drawer. Filtered white noise, very short.
  const frames = Math.floor(ctx.sampleRate * 0.05);
  const buffer = ctx.createBuffer(1, frames, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < frames; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / frames);
  const noise = ctx.createBufferSource();
  noise.buffer = buffer;
  const band = ctx.createBiquadFilter();
  band.type = "bandpass";
  band.frequency.value = 2400;
  band.Q.value = 1.1;
  const clack = ctx.createGain();
  clack.gain.value = 0.35;
  noise.connect(band).connect(clack).connect(ctx.destination);
  noise.start(now);

  // The ring, a major third above, struck twice.
  strike(now + 0.02, 1318.5, [1, 2.01, 3.02], 0.85, 0.22);
  strike(now + 0.09, 1661.2, [1, 2.01, 3.02], 1.15, 0.20);
}

/**
 * A buzzer: a low square tone, hard on and hard off, pulsed twice.
 * Square rather than sine because the odd harmonics are what make it unpleasant,
 * and it should be unpleasant — this is the sound of losing money.
 */
export function buzzer(): void {
  if (!ctx) return;
  const now = ctx.currentTime;
  for (const offset of [0, 0.24]) {
    const osc = ctx.createOscillator();
    const env = ctx.createGain();
    osc.type = "square";
    osc.frequency.setValueAtTime(150, now + offset);
    // A slight downward slide. Falling pitch reads as failure across every culture
    // that has ever built an arcade machine.
    osc.frequency.linearRampToValueAtTime(118, now + offset + 0.17);
    env.gain.setValueAtTime(0, now + offset);
    env.gain.linearRampToValueAtTime(0.16, now + offset + 0.01);
    env.gain.setValueAtTime(0.16, now + offset + 0.15);
    env.gain.linearRampToValueAtTime(0, now + offset + 0.17);
    osc.connect(env).connect(ctx.destination);
    osc.start(now + offset);
    osc.stop(now + offset + 0.2);
  }
}

export const CUES = { openingBell, closingBell, cashRegister, buzzer } as const;
export type Cue = keyof typeof CUES;
