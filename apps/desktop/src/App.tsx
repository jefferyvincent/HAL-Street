import { ChromeBar } from "@/components/ChromeBar";
import { HaltBanner } from "@/components/HaltBanner";
import { Rail } from "@/components/Rail";
import { StatusBar } from "@/components/StatusBar";
import { Tape } from "@/components/Tape";
import { GRID } from "@/constants/theme";
import { useAudioCues } from "@/hooks/useAudioCues";
import { useConnect } from "@/hooks/useConnect";
import { useDecisions } from "@/hooks/useDecisions";
import { useGateFamilies } from "@/hooks/useGateFamilies";
import { useShortcuts } from "@/hooks/useShortcuts";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";
import { useUI } from "@/stores/ui";
import { BookView, ConsoleView, GatesView, JournalView } from "@/views";

const VIEWS = {
  console: ConsoleView,
  journal: JournalView,
  gates: GatesView,
  book: BookView,
} as const;

export default function App() {
  const t = useStrings();
  const snap = useConnection((s) => s.snapshot);
  const view = useUI((s) => s.view);
  const decisions = useDecisions();
  const families = useGateFamilies(decisions.current);

  useConnect();
  useShortcuts(decisions);
  // Sounds the bell and the trade cues. Silent until the operator turns audio on,
  // and silent on the first snapshot whatever the setting — opening a dashboard is
  // not an event, and replaying the morning is not a notification.
  useAudioCues(snap);

  const View = VIEWS[view];
  // The rails describe the selected decision, so they belong to the console. The
  // other two views take the full width rather than compete with a narrower copy of
  // themselves down the right-hand side.
  const wide = view !== "console";

  return (
    <div className="flex h-full flex-col bg-void">
      <ChromeBar />
      <HaltBanner />
      {snap ? (
        <div className={wide ? GRID.wide : GRID.console}>
          {!wide && <Rail families={families} />}
          <main className="min-w-0 bg-void p-3">
            <View />
          </main>
          {!wide && <Tape rows={decisions.rows} selected={decisions.selected} />}
        </div>
      ) : (
        <div className="flex flex-1 items-center justify-center font-mono text-[12px] text-ink/40">
          {t.app.waiting}
        </div>
      )}
      <StatusBar families={families} />
    </div>
  );
}
