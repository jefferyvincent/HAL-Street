import { ICON } from "@/constants/icons";
import { cn } from "@/lib/cn";
import { useStrings } from "@/hooks/useStrings";
import { useSoundToggle } from "@/hooks/useAudioCues";
import { Icon } from "./Icon";

/**
 * The only control in the panel, and it changes nothing about the account.
 *
 * A button rather than a preference read at load, because browsers will not start
 * audio outside a real gesture: an AudioContext created on mount stays suspended,
 * so a toggle that merely set a flag would read as on and make no sound at all.
 */
export function SoundToggle() {
  const t = useStrings();
  const { muted, toggle } = useSoundToggle();
  return (
    <button
      onClick={() => void toggle()}
      title={t.chrome.soundTitle}
      aria-pressed={!muted}
      className={cn(
        "flex items-center gap-[7px] border-l border-line px-3 font-mono text-[11px] font-semibold leading-none",
        "transition-colors hover:text-ink focus-visible:outline focus-visible:outline-1 focus-visible:outline-amber",
        muted ? "text-mute" : "text-amber",
      )}
    >
      <Icon d={muted ? ICON.muted : ICON.sound} stroke="currentColor" />
      {muted ? t.chrome.soundOff : t.chrome.soundOn}
    </button>
  );
}
