/**
 * The snapshot, as the server actually sends it.
 *
 * Two rules run through these types and both come from the Python side.
 *
 * Money is `string`, never `number`. The journal's rule is Decimal in and Decimal
 * out, and `_plain()` serialises every Decimal as a string so nothing is rounded on
 * the way to a screen. Typing them as `number` here would reintroduce, in the one
 * place a human reads the figure, exactly the float the rest of the system refuses.
 * Formatting parses at the edge; the values are carried as sent.
 *
 * `family` and the fields beside it are optional because the journal is append-only
 * and older records predate them. They are not "maybe missing" in the sense of a bug
 * — they are history, and the panel resolves them against the served chain instead.
 */

export type Family = "contract" | "liquidity" | "defined_risk" | "portfolio" | "circuit";

export interface GateVerdict {
  gate: string;
  passed: boolean;
  reason: string;
  family?: string;
}

export interface ChainEntry {
  gate: string;
  family: string;
}

export interface Leg {
  symbol: string;
  side?: string;
  ratio_qty?: number;
}

export interface StructureDetail {
  limit_price?: string | null;
  qty?: number | null;
  legs?: Leg[];
}

export interface Decision {
  ts: string;
  event: string;
  approved: boolean;
  structure?: string;
  underlying?: string;
  gates?: GateVerdict[];
  rejected_by?: string[];
  rationale?: string;
  confidence?: string | number | null;
  structure_detail?: StructureDetail;
}

export interface Circuit {
  halted: boolean;
  halt_reason: string;
  baseline_equity: string | null;
  baseline_day: string | null;
  entries_this_hour: number;
  describe: string;
}

export interface Pnl {
  realized: string;
  unrealized: string;
  total: string;
  wins: number;
  losses: number;
  open: number;
  closed: number;
  proposals: number;
  passed: number;
  approved: number;
  rejected: number;
  orders_submitted: number;
  rejections_by_gate: Record<string, number>;
  equity_start: string | null;
  equity_last: string | null;
  max_drawdown_usd: string;
  max_drawdown_pct: string;
  equity_samples: number;
}

export interface Position {
  structure_id: string;
  name: string;
  underlying: string;
  qty: number;
  opened_at: string;
  rationale: string;
  legs: Record<string, number>;
  entry_price: string | null;
}

export interface ClosedStructure {
  structure_id: string;
  name: string;
  underlying: string;
  qty: number;
  opened_at: string;
  closed_at: string | null;
  entry_price: string | null;
  exit_price: string | null;
  realized_usd: string | null;
  rationale: string;
}

/** The levels the exit policy acts on, in mark space — what the chart draws. */
export interface ExitLevels {
  entry: string;
  target: string;
  stop: string;
  /** True for a credit structure, where a rising mark is profit toward zero. */
  credit: boolean;
  /**
   * False when the policy's stop sits at a price the market cannot print — a long
   * structure whose stop is more than 100% of the premium paid. The level is clamped
   * to zero so it is drawable and true; this flag is what stops the line being read
   * as a threshold the policy would act on.
   */
  stop_reachable: boolean;
}

export interface StructureChart {
  structure_id: string;
  name: string;
  underlying: string;
  qty: number;
  open: boolean;
  opened_at: string;
  closed_at: string | null;
  dte: number | null;
  legs: { symbol: string; signed: number }[];
  /** The structure's own net price over time, not a single leg's. */
  series: { t: string; v: string }[];
  /** Null when the entry price is unknown — the panel says so rather than guessing. */
  levels: ExitLevels | null;
  entry_filled: boolean;
  exit_price: string | null;
  exit_filled: boolean;
  policy: { take_profit_pct: string; stop_loss_pct: string; force_close_dte: number };
  realized_usd: string | null;
  /** Present when the price history could not be fetched; levels are still drawable. */
  error?: string;
}

export interface EquityPoint {
  t: string;
  v: string;
}

export interface MarketView {
  ts: string;
  underlying: string;
  profile?: string;
  bias?: string;
  bias_reasons?: string[];
  regime?: string;
}

export interface Menu {
  ts: string;
  underlying: string;
  count: number;
  candidates?: unknown[];
}

/**
 * The last session transition the scheduler wrote down.
 *
 * Null until a scheduled run has written one: a `--once` run never observes the
 * closed half of a session, and the panel says nothing rather than inferring a
 * session from a local clock that knows no holidays or early closes.
 */
export interface Market {
  state: "open" | "closed";
  /** When the transition was journalled. */
  at: string;
  session_date: string | null;
  next_open: string | null;
  next_close: string | null;
  /**
   * True when the scheduler merely *found* this state on startup rather than
   * hearing it change. The difference between ringing a bell and labelling one.
   */
  observed: boolean;
}

export interface Snapshot {
  chain: ChainEntry[];
  families: string[];
  limits: Record<string, string>;
  circuit: Circuit;
  pnl: Pnl;
  positions: Position[];
  closed: ClosedStructure[];
  decisions: Decision[];
  equity_curve: EquityPoint[];
  views: MarketView[];
  menus: Menu[];
  market: Market | null;
}

/** What the socket sends between snapshots — proof of life, not data. */
export interface Heartbeat {
  heartbeat: true;
}

export type Push = Snapshot | Heartbeat;

export const isHeartbeat = (m: Push): m is Heartbeat =>
  (m as Heartbeat).heartbeat === true;
