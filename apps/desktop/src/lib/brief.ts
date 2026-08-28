import type { Burn, Menu } from "@/types";

/**
 * The brief: every structure the deterministic side built, and how each one sits
 * against the read.
 *
 * This is what HAL Street actually hands the committee, and it was written to the
 * journal from the very first session and drawn nowhere. The tab carried four
 * paragraphs of argument with no sight of the thing being argued about — which is how
 * a screen that full still reads as dead, and why the menu belongs above the seats
 * rather than behind them.
 *
 * Two sources, and which one is available says where the cycle is. The scored table
 * arrives with the finished session, because the fit is worked out against the
 * catalyst's read. The bare menu is on the journal a stage earlier — most of a minute
 * before anything else, and the whole of the stretch that looked like nothing was
 * happening.
 *
 * The fit is never computed here. It is a rule, it lives in `strategy/burn.py`, and a
 * second implementation on this side would be a second answer to the same question
 * with no test holding them together. An unscored structure says so instead.
 *
 * No words here, by rule.
 */

export interface BriefSource {
  /** The finished session's scored table, when there is one. */
  burn: Burn | null;
  /** The menu as journalled, for a cycle whose committee has not landed yet. */
  menu: Menu | null;
}

export interface BriefRow {
  key: string;
  name: string;
  kind: string;
  /** Null when nobody has scored it against a read yet — which is not "ambient". */
  fit: "fits" | "against" | "ambient" | null;
  why: string | null;
  netPrice: string;
  maxLoss: string;
  maxGain: string;
  pop: number;
  score: string;
}

/** One row per structure, in the order the ranking put them. */
export function briefRows({ burn, menu }: BriefSource): BriefRow[] {
  const scored = burn?.structures ?? [];
  if (scored.length > 0) {
    return scored.map((s, i) => ({
      key: `${s.name}-${i}`,
      name: s.name,
      kind: s.kind,
      fit: s.news_fit,
      why: s.why,
      netPrice: s.net_price,
      maxLoss: s.max_loss_usd,
      maxGain: s.max_gain_usd,
      pop: s.prob_of_profit,
      score: s.score,
    }));
  }
  // `candidates` is optional on the record: older events counted without listing, and
  // a cycle that built nothing writes a count and no list at all.
  const built = (menu?.candidates ?? []) as Partial<BriefRow & {
    net_price: string; max_loss_usd: string; max_gain_usd: string;
    prob_of_profit: number;
  }>[];
  return built.map((c, i) => ({
    key: `${c.name ?? i}-${i}`,
    name: String(c.name ?? ""),
    kind: String(c.kind ?? ""),
    fit: null,
    why: null,
    netPrice: String(c.net_price ?? ""),
    maxLoss: String(c.max_loss_usd ?? ""),
    maxGain: String(c.max_gain_usd ?? ""),
    pop: Number(c.prob_of_profit ?? 0),
    score: String(c.score ?? ""),
  }));
}
