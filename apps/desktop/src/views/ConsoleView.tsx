import { cn } from "@/lib/cn";
import { ICON } from "@/constants/icons";
import { CLS, GRID, STROKE } from "@/constants/theme";
import { ActivityFeed } from "@/components/ActivityFeed";
import { EquityChart } from "@/components/EquityChart";
import { Scoreboard } from "@/components/Scoreboard";
import { Holding } from "@/components/Holding";
import { Periods } from "@/components/Periods";
import { Spend } from "@/components/Spend";
import { GateLedger } from "@/components/GateLedger";
import { Cross, Icon, Note, Tick } from "@/components/Icon";
import { Ticker } from "@/components/Ticker";
import { useDecisionFacts } from "@/hooks/useDecisionFacts";
import { useDecisions } from "@/hooks/useDecisions";
import { useFormat } from "@/hooks/useFormat";
import { useGateFamilies } from "@/hooks/useGateFamilies";
import { useStrings } from "@/hooks/useStrings";
import { useVerdict } from "@/hooks/useVerdict";
import { useConnection } from "@/stores/connection";
import { useUI } from "@/stores/ui";

/**
 * One decision, in full.
 *
 * Also the mockup's decision-record screen: there is no separate view for it because
 * this already is one — the journal table selects into here rather than duplicating
 * the same fields somewhere else.
 */
export function ConsoleView() {
  const t = useStrings();
  const f = useFormat();
  const { current } = useDecisions();
  const snap = useConnection((s) => s.snapshot);
  const chart = useUI((s) => s.chart);
  const decisionOpen = useUI((s) => s.decisionOpen);
  const toggleDecision = useUI((s) => s.toggleDecision);
  const families = useGateFamilies(current);
  const facts = useDecisionFacts(current);
  const verdict = useVerdict(current);

  // Not a dead end when there is nothing. Nothing has been gated because nothing has
  // been proposed, which is the ordinary outcome — so the run's own numbers stay on
  // screen rather than a sentence that reads as "broken".
  const run = (
    <>
      <Scoreboard />
      <Periods />
      {snap && <EquityChart curve={snap.equity_curve} pnl={snap.pnl} />}
      <Holding />
      <Spend />
    </>
  );

  if (!current || !verdict) {
    return (
      <div className="mb-3 flex flex-col gap-3">
        {run}
        <div className="border border-edge bg-panel">
          <div className={CLS.empty}>{t.console.none}</div>
        </div>
        <ActivityFeed />
      </div>
    );
  }

  return (
    <div className="mb-3 flex flex-col gap-3">
      {run}
    <div className={cn("border bg-panel", verdict.ok ? "border-edge" : "border-fail")}>
      <div className={cn("flex flex-wrap items-center gap-[9px] border-b px-3 py-[9px]",
        verdict.ok ? "border-b-pass/40 bg-pass/12" : "border-b-fail/45 bg-fail/14")}>
        {verdict.ok ? <Tick /> : <Cross />}
        <Ticker symbol={current.underlying ?? t.common.unknown} />
        <span className={cn("font-mono text-[11px] font-bold leading-none tracking-[.1em]",
          verdict.ok ? "text-pass" : "text-fail")}>
          {verdict.label}
        </span>
        <span className="flex-1" />
        {/* Through to the position, when the decision became one. The only way
            here used to be BOOK, and nothing said the two were the same trade. */}
        {current.structure_id && (
          <button
            onClick={() => chart(current.structure_id!)}
            className="font-mono text-[10px] font-bold leading-none tracking-[.08em] text-amber
                       transition-opacity hover:opacity-70 focus-visible:outline
                       focus-visible:outline-1 focus-visible:outline-amber">
            {t.console.openTrade}
          </button>
        )}
        <span className="font-mono text-[10.5px] font-medium leading-none text-ink/40">
          {f.clock(current.ts)}
        </span>
        {/* The record is a rationale and sixteen verdicts. The verdict itself is in
            this header, so the rest opens on request rather than pushing the run's
            numbers and the open book off the top of the view. */}
        <button
          onClick={toggleDecision}
          aria-expanded={decisionOpen}
          className="flex items-center gap-[5px] font-mono text-[10px] font-bold leading-none
                     tracking-[.08em] text-ink/45 transition-colors hover:text-ink
                     focus-visible:outline focus-visible:outline-1 focus-visible:outline-amber">
          <Icon d={ICON.chevron} size={12} stroke="currentColor" width={2.4}
                className={decisionOpen ? "rotate-180" : ""} />
          {decisionOpen ? t.console.collapse : t.console.expand}
        </button>
      </div>

      {decisionOpen && (<>

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
            {facts.map((fact) => (
              <div key={fact.key} className="bg-void px-[10px] py-[9px]">
                <div className="font-mono text-[8.5px] font-bold leading-none tracking-[.08em] text-ink/40">
                  {fact.label}
                </div>
                <div className={cn("mt-[5px] font-mono text-[13px] font-semibold leading-none tabular-nums",
                  fact.good ? "text-pass" : "text-ink")}>
                  {fact.value}
                </div>
              </div>
            ))}
          </div>

          {verdict.failed.length > 0 && (
            <div className="mt-3 border border-fail/40">
              <div className="bg-fail/14 px-[11px] py-[7px] font-mono text-[9.5px] font-bold leading-none tracking-[.1em] text-fail">
                {t.console.rejectReasons}
              </div>
              {verdict.failed.map((g) => (
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

        <GateLedger families={families} total={verdict.total} failed={verdict.failed.length} />
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
    </>)}
    </div>
    </div>
  );
}
