import { cn } from "@/lib/cn";
import { ICON } from "@/constants/icons";
import { CLS, STROKE } from "@/constants/theme";
import { ActivityFeed } from "@/components/ActivityFeed";
import { Icon, Note } from "@/components/Icon";
import { Ticker } from "@/components/Ticker";
import { useAgentPass, type PassLine, type PassStep } from "@/hooks/useAgentPass";
import { useCommitteeDesk } from "@/hooks/useCommitteeDesk";
import { useStrings } from "@/hooks/useStrings";

/**
 * What the agent is doing, name by name, while it does it.
 *
 * The panel could say what was happening *right now* and what had been decided
 * *eventually*, with nothing in between. A pass over six discovered names is a minute
 * or two in which four are settled and one is mid-committee, and that shape — the
 * queue, and where in it the agent has got to — was on no screen.
 *
 * Scan order, never sorted by outcome. It is a queue being worked through, and
 * re-ordering it loses the only thing the table is for.
 *
 * Three things, in the order you would ask them: what is it on, how far has the pass
 * got, and what has it actually written down.
 */
export function AgentView() {
  const t = useStrings();
  const pass = useAgentPass();
  const desk = useCommitteeDesk();

  return (
    <div className="mb-3 flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 border border-line bg-panel px-3 py-[9px]">
        <Icon d={ICON.pulse} stroke={STROKE.amber} width={2.2} />
        <span className="font-mono text-[10px] font-bold leading-none tracking-[.12em] text-ink/60">
          {pass.title}
        </span>
        <span className="font-sans text-[10.5px] leading-none text-ink/40">{pass.meta}</span>
        {pass.started && (
          <span className="font-mono text-[9.5px] leading-none text-ink/25">{pass.started}</span>
        )}
        <span className="flex-1" />
        {/* The same live state the committee rail and the chrome bar carry, from the
            same record. Three places saying it is one fact, not three. */}
        {desk.sitting ? (
          <span className="flex items-center gap-[6px] font-mono text-[10px] font-bold leading-none tracking-[.08em] text-amber">
            <span className={cn(CLS.dot, "desk-dot bg-amber")} />
            {desk.stage}
          </span>
        ) : desk.idle && (
          <span className={cn("font-mono text-[9.5px] leading-none", desk.idle.tone)}>
            {desk.idle.title}
          </span>
        )}
      </div>

      {pass.empty ? (
        <div className={cn(CLS.empty, "border border-line bg-panel")}>{pass.empty}</div>
      ) : (
        <div className="border border-line bg-panel">
          {pass.rows.map((row) => <Row key={row.key} row={row} />)}
        </div>
      )}

      <ActivityFeed />
      <Note>{t.agent.pulseNote}</Note>
    </div>
  );
}

/** One name: where it got to, and what came of it. */
function Row({ row }: { row: PassLine }) {
  return (
    <div className={cn("flex flex-wrap items-center gap-x-[10px] gap-y-[6px]",
      "border-b border-line-soft px-3 py-[10px] last:border-b-0",
      row.running && "desk-busy")}>
      <Ticker symbol={row.underlying} />
      {row.spot && (
        <span className="font-mono text-[9.5px] leading-none tabular-nums text-ink/25">
          {row.spot}
        </span>
      )}

      <ol className="flex items-center gap-[3px]">
        {row.steps.map((step) => <Step key={step.key} step={step} />)}
      </ol>

      {row.read && (
        <span className="shrink-0 font-mono text-[9.5px] leading-none text-ink/35">
          {row.read.text}
          {row.read.reach && (
            <span className="ml-[7px] text-ink/20">{row.read.reach}</span>
          )}
        </span>
      )}

      {row.detail && (
        <span className="min-w-0 flex-1 truncate font-sans text-[10.5px] leading-[1.4] text-ink/40">
          {row.detail}
        </span>
      )}
      <span className="flex-1" />
      <span className={cn("shrink-0 font-mono text-[9.5px] font-bold leading-none tracking-[.1em]",
        row.outcomeTone)}>
        {row.outcome}
      </span>
    </div>
  );
}

/**
 * One step of the cycle. Every one is drawn, including those that will never run.
 *
 * `skipped` is hollow rather than absent, because the shape is the information: a name
 * whose menu came up empty has no deliberation missing and none coming, and a track
 * that simply stopped would read as one still in progress.
 */
function Step({ step }: { step: PassStep }) {
  const style = step.state === "working" ? "desk-dot border-amber bg-amber/70 text-amber"
    : step.state === "done" ? "border-amber/50 bg-amber/25 text-ink/55"
    : step.state === "failed" ? "border-fail/60 bg-fail/20 text-fail/80"
    : step.state === "held" ? "border-amber/40 text-amber/60"
    : step.state === "empty" ? "border-ink/25 text-ink/30"
    : step.state === "skipped" ? "border-line border-dashed text-ink/15"
    : "border-line text-ink/20";

  return (
    <li className={cn("border px-[5px] py-[3px] font-mono text-[8px] font-bold",
      "leading-none tracking-[.1em]", style)}>
      {step.label}
    </li>
  );
}
