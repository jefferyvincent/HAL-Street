import { cn } from "@/lib/cn";
import { clock } from "@/lib/format";
import { ICON } from "@/constants/icons";
import { CLS, GRID, STROKE } from "@/constants/theme";
import { ActivityFeed } from "@/components/ActivityFeed";
import { GateLedger } from "@/components/GateLedger";
import { Cross, Icon, Note, Tick } from "@/components/Icon";
import { useDecisionFacts } from "@/hooks/useDecisionFacts";
import { useDecisions } from "@/hooks/useDecisions";
import { useGateFamilies } from "@/hooks/useGateFamilies";
import { useStrings } from "@/hooks/useStrings";

/**
 * One decision, in full.
 *
 * Also the mockup's decision-record screen: there is no separate view for it because
 * this already is one — the journal table selects into here rather than duplicating
 * the same fields somewhere else.
 */
export function ConsoleView() {
  const t = useStrings();
  const { current } = useDecisions();
  const families = useGateFamilies(current);
  const facts = useDecisionFacts(current);

  if (!current) {
    // Not a dead end. Nothing has been gated because nothing has been proposed,
    // which is the ordinary outcome — so show what the agent is actually doing
    // rather than a sentence that reads as "broken".
    return (
      <div className="mb-3 flex flex-col gap-3">
        <div className="border border-edge bg-panel">
          <div className={CLS.empty}>{t.console.none}</div>
        </div>
        <ActivityFeed />
      </div>
    );
  }

  const gates = current.gates ?? [];
  const failed = gates.filter((g) => !g.passed);
  const ok = current.approved;

  return (
    <div className={cn("mb-3 border bg-panel", ok ? "border-edge" : "border-fail")}>
      <div className={cn("flex items-center gap-[9px] border-b px-3 py-[9px]",
        ok ? "border-b-pass/40 bg-pass/12" : "border-b-fail/45 bg-fail/14")}>
        {ok ? <Tick /> : <Cross />}
        <span className={cn("font-mono text-[11px] font-bold leading-none tracking-[.1em]",
          ok ? "text-pass" : "text-fail")}>
          {ok ? t.console.approved(gates.length) : t.console.rejected(failed.length, gates.length)}
        </span>
        <span className="flex-1" />
        <span className="font-mono text-[10.5px] font-medium leading-none text-ink/40">
          {current.underlying} · {clock(current.ts)}
        </span>
      </div>

      <div className={GRID.decision}>
        <div className="min-w-0 border-r border-edge p-[14px]">
          <div className="font-mono text-[15px] font-semibold leading-[1.2] break-words text-ink">
            {current.structure}
          </div>

          {current.rationale && (
            <div className="mt-[10px] border-l-2 border-agent/40 bg-void px-3 py-[10px] font-sans text-[12px] leading-[1.55] text-ink/60">
              <span className="mb-[5px] block font-mono text-[9px] font-bold leading-none tracking-[.1em] text-agent">
                {t.console.rationale}
              </span>
              {current.rationale}
            </div>
          )}

          <div className="mt-[10px] grid grid-cols-3 gap-px bg-line">
            {facts.map((f) => (
              <div key={f.key} className="bg-void px-[10px] py-[9px]">
                <div className="font-mono text-[8.5px] font-bold leading-none tracking-[.08em] text-ink/40">
                  {f.key}
                </div>
                <div className={cn("mt-[5px] font-mono text-[13px] font-semibold leading-none tabular-nums",
                  f.good ? "text-pass" : "text-ink")}>
                  {f.value}
                </div>
              </div>
            ))}
          </div>

          {failed.length > 0 && (
            <div className="mt-3 border border-fail/40">
              <div className="bg-fail/14 px-[11px] py-[7px] font-mono text-[9.5px] font-bold leading-none tracking-[.1em] text-fail">
                {t.console.rejectReasons}
              </div>
              {failed.map((g) => (
                <div key={g.gate} className="flex gap-[9px] border-b border-line-soft bg-void px-[11px] py-[10px] last:border-b-0">
                  <Cross />
                  <div>
                    <div className="font-mono text-[11.5px] font-semibold leading-[1.2] text-fail-ink">{g.gate}</div>
                    <div className="mt-1 font-sans text-[11.5px] leading-[1.5] text-ink/68">{g.reason}</div>
                  </div>
                </div>
              ))}
            </div>
          )}

          <Note>{t.console.noOverride}</Note>
        </div>

        <GateLedger families={families} total={gates.length} failed={failed.length} />
      </div>

      {current.confidence != null && (
        <div className="m-3 mt-0 flex gap-2 border border-line bg-void px-[10px] py-[9px] font-sans text-[10.5px] leading-[1.45] text-ink/40">
          <Icon d={ICON.info} size={12} stroke={STROKE.agent} width={2.2} />
          <span>
            <span className="font-mono tabular-nums text-agent">
              {t.console.confidence(String(current.confidence))}
            </span>{" "}
            {t.console.confidenceNote}
          </span>
        </div>
      )}
    </div>
  );
}
