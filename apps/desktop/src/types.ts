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
  /**
   * The position this decision became, when it became one. Null for a rejection, a
   * dry run, or an order that was never sent — the panel then offers no link rather
   * than one to a trade that does not exist.
   */
  structure_id: string | null;
  ts: string;
  event: string;
  approved: boolean;
  /**
   * Whether the cycle that produced this verdict would have submitted. Null for a
   * record written before the agent stamped it and whose cycle cannot be recovered.
   *
   * An APPROVED that sent nothing and an APPROVED that sent an order are the same
   * six letters, and nobody should have to correlate two records to tell a rehearsal
   * from a trade.
   */
  dry_run: boolean | null;
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
  /**
   * Which way this structure wants the underlying to go. A property of the whole
   * spread, not of a leg: a put credit spread is short a put and long a further
   * put, reads "bearish" leg by leg, and is bullish.
   */
  exposure: "bullish" | "bearish" | "neutral" | "unknown";
  /** Every confirmed pattern on the underlying, shown whether or not it bears. */
  patterns: Pattern[];
  /** Those that run against the exposure. A list to read, never a verdict to act on. */
  against: Pattern[];
  confirming: Pattern[];
  /**
   * The agent's own most recent judgement of this position, from the journal.
   * Null until a cycle has priced it. A cycle old, not live — the snapshot must
   * not reach the broker, and `as_of` says when it was taken.
   */
  read: {
    mark: string | null;
    unrealized_usd: string | null;
    dte: number | null;
    action: string;
    reason: string;
    as_of: string;
  } | null;
  /**
   * Every mark the agent has taken of this position, oldest first — its own record,
   * one point per cycle, not a price feed.
   *
   * `pnl` is what the card plots. The mark would be the wrong series to draw: every
   * structure here is a credit, so its mark rises as the position loses, and a line
   * of marks slopes downward on a winning trade.
   */
  marks?: { t: string; v: string; pnl: string | null }[];
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
  /**
   * Each leg with the price it filled at on the way in, and — once closed — on the
   * way out. Both come off the order's own `legs` array, so they belong to this
   * structure rather than to whatever the broker has netted under that symbol.
   */
  legs: {
    symbol: string;
    /** Signed contracts per structure, before size. */
    signed: number;
    /** And after it: what the account actually holds for this structure. */
    contracts: number;
    basis: string | null;
    exit: string | null;
    realized_usd: string | null;
  }[];
  /** The structure's own net price over time, not a single leg's. */
  series: { t: string; v: string }[];
  /**
   * The same prices as one candle per session, bucketed from the observed net.
   * Never summed from the legs' own highs and lows: the legs move together, so a
   * summed range spans prices the structure was never at.
   */
  candles: {
    t: string; o: string; h: string; l: string; c: string;
    /** True while this candle's bucket is the one the clock is in. */
    forming: boolean;
  }[];
  /** Null when the entry price is unknown — the panel says so rather than guessing. */
  levels: ExitLevels | null;
  entry_filled: boolean;
  exit_price: string | null;
  exit_filled: boolean;
  policy: { take_profit_pct: string; stop_loss_pct: string; force_close_dte: number };
  realized_usd: string | null;
  /** The bar size actually used. */
  timeframe?: string;
  /** What else can be asked for. Served, so the panel cannot drift from the real set. */
  timeframes?: string[];
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
  /**
   * How the state above was arrived at:
   *
   *   observed   the agent is running and wrote this crossing down
   *   boundary   nobody wrote it down, but the broker had published when it would
   *              happen and that time has passed
   *   last-seen  no boundary to reason from and nothing writing — we do not know
   */
  source: "observed" | "boundary" | "last-seen";
  /** What the journal said, beside what was concluded from it. */
  recorded: "open" | "closed" | null;
  /** The broker-published boundary the state was derived from, when it was. */
  crossed_at: string | null;
  /** Whether anything is still running that could write the next boundary. */
  stale: boolean;
  /** How long the journal has been silent, in seconds. Null if it has never spoken. */
  quiet_for_s: number | null;
}

/** One confirmed setup on the underlying's daily bars. */
export interface Pattern {
  name: string;
  side: "bullish" | "bearish" | "neutral";
  /** Where it triggered — a level, not a prediction. */
  note: string;
}

/** One analyst's read. Neutral and unconfident is the designed failure mode. */
export interface Verdict {
  lean: "bullish" | "bearish" | "neutral";
  confidence: number;
  note: string;
}

/** A committee session: the deliberation behind one proposal, and what came of it. */
export interface Committee {
  ts: string;
  underlying: string;
  headlines: number;
  catalyst: Verdict;
  bull: string;
  bear: string;
  reflection: { structure: string; realized_usd: string | null; outcome: string }[];
  tokens: { in: number; out: number; cache_read: number };
  /**
   * The same spend per stage, with the model that produced it. The three research
   * stages run a tier below the judge, so one total no longer has a price.
   */
  stages: Record<string, {
    in: number; out: number; cache_read: number; model: string | null;
  }>;
  /** Stages that failed. The cycle continues; the judge is told. */
  errors: string[];
  outcome: {
    passed: boolean;
    ok: boolean;
    rationale: string;
    structure: string;
    error: string | null;
    approved: boolean | null;
    rejected_by: string[];
  };
}

/** One line of what the agent is doing, as opposed to what it decided. */
export interface Activity {
  ts: string;
  event: string;
  underlying: string;
  detail: string;
}

/**
 * What the agent is in the middle of, or null when it is between cycles.
 *
 * Derived on the server from the last record written plus a clock, not pushed by the
 * agent — so a process that dies mid-cycle stops looking busy on its own rather than
 * spinning forever.
 */
export interface InFlight {
  /** What the stage is doing, in words. */
  stage: string;
  /** The journal event it was derived from. */
  event: string;
  underlying: string;
  since: string;
}

/** What one gate measured the last time it ran. Its own words, not a recomputation. */
export interface GateReading {
  reason: string;
  passed: boolean;
  at: string;
  /** The structure it was reading against. */
  structure: string;
}

/**
 * One article the catalyst read. Untrusted publisher text: render as text, never as
 * markup, and never treat as an instruction.
 */
export interface NewsItem {
  ts: string;
  /** Null when the publisher's timestamp could not be trusted. */
  age_hours: number | null;
  source: string;
  headline: string;
  /** Every symbol the publisher tagged. */
  symbols: string[];
  /** Which of our own underlyings' reads picked it up. */
  roots: string[];
  /**
   * The publisher's page. Empty unless it passed the server's scheme allowlist —
   * this is the one piece of untrusted input a browser will *execute* rather than
   * display, so it is validated once, on the server, and taken as given here.
   */
  url: string;
}

/** What the model calls have cost. Tokens always; money where a price is configured. */
export interface Spend {
  total: { in: number; out: number; cache_read: number };
  cycles: number;
  models: {
    model: string; in: number; out: number; cache_read: number;
    /** Null when this model has no configured price — never zero, which is a claim. */
    cost_usd: string | null;
  }[];
  /** Counted tokens no stage accounted for: cycles run before per-stage accounting. */
  unattributed: { in: number; out: number; cache_read: number };
  cost_usd: string;
  /** True when some counted tokens had no price, making `cost_usd` a floor. */
  partial: boolean;
  prices: Record<string, { in: string; out: string }>;
}

/** P&L over one calendar window. Realized and mark-to-market are different numbers. */
export interface Period {
  period: "day" | "week" | "month" | "year" | "all";
  /** First session in the window; null for "all". */
  start: string | null;
  /** What closed trades made in it. Exact, off the ledger. */
  realized_usd: string;
  closed: number;
  /**
   * Equity change across the window, or null when the journal does not reach back to
   * its start. Null rather than a figure that would silently mean "since this file
   * was created".
   */
  equity_change_usd: string | null;
  covered: boolean;
  /** The first session the journal has any equity for. */
  since: string | null;
}

export interface Snapshot {
  chain: ChainEntry[];
  families: string[];
  limits: Record<string, string>;
  circuit: Circuit;
  /**
   * Whether the last cycle would have submitted. True live, false a rehearsal, null
   * when nothing has scanned yet — three values, because "we do not know" and "it is
   * live" must never render the same.
   */
  armed: boolean | null;
  in_flight: InFlight | null;
  gate_readings: Record<string, GateReading>;
  spend: Spend;
  periods: Period[];
  headlines: NewsItem[];
  pnl: Pnl;
  positions: Position[];
  closed: ClosedStructure[];
  decisions: Decision[];
  equity_curve: EquityPoint[];
  views: MarketView[];
  menus: Menu[];
  market: Market | null;
  activity: Activity[];
  committees: Committee[];
}

/** One leg of an open structure, priced. All dollar figures are scaled by size. */
export interface LegMark {
  symbol: string;
  signed: number;
  contracts: number;
  bid: string | null;
  ask: string | null;
  mid: string | null;
  /** What it filled at per contract, from the opening order. Null if never recorded. */
  basis: string | null;
  value_usd: string | null;
  unrealized_usd: string | null;
}

/** Live marks for open structures, from the one route that reaches the broker. */
export interface Marks {
  marks: Record<string, {
    mark?: string;
    unrealized_usd?: string | null;
    /** Legs that could not be priced. A partial mark is not a mark. */
    missing?: string[];
    /**
     * Every leg priced individually. Sent even when the net refuses to price — a
     * structure missing a quote is exactly when you want to see which leg is missing
     * it and what the others are doing.
     *
     * `unrealized_usd` here sums to the structure's own, because the leg fills sum to
     * the net fill and the leg mids sum to the net mark.
     */
    legs?: LegMark[];
  }>;
  as_of: string;
  error?: string;
}

/** What the socket sends between snapshots — proof of life, not data. */
export interface Heartbeat {
  heartbeat: true;
}

export type Push = Snapshot | Heartbeat;

export const isHeartbeat = (m: Push): m is Heartbeat =>
  (m as Heartbeat).heartbeat === true;
