import { useMemo } from "react";

import { useFormat } from "@/hooks/useFormat";
import { useStrings } from "@/hooks/useStrings";
import { useConnection } from "@/stores/connection";

export interface SpendModel {
  model: string;
  split: string;
  /** The words where no price is configured, so the row is never a smaller number. */
  cost: string;
  priced: boolean;
}

export interface SpendCard {
  cycles: string;
  /** The headline, already carrying its "at least" qualifier where it is a floor. */
  total: string;
  figures: { key: string; label: string; value: string; note?: string }[];
  models: SpendModel[];
  /** Tokens spent before per-stage accounting existed, or null when there are none. */
  stray: SpendModel | null;
  /** The first model with no configured price, for the footnote naming one. */
  unpriced: string | null;
}

/**
 * What the thinking cost, split by model and priced where a price is known.
 *
 * **The dollar figure is a floor, and the card says so when it is one.** A model with
 * no configured price contributes its tokens and no cost; that qualifier is attached
 * to the number here rather than printed near it, so the two cannot be read apart.
 */
export function useSpend(): SpendCard | null {
  const t = useStrings();
  const f = useFormat();
  const spend = useConnection((s) => s.snapshot?.spend);

  return useMemo(() => {
    if (!spend) return null;
    const { total, models, unattributed, cycles } = spend;

    const priced = (cost: string | null) =>
      cost === null ? t.spend.noPrice : f.money(cost);

    const strayTokens = unattributed.in + unattributed.out > 0;

    return {
      cycles: t.spend.cycles(cycles),
      total: spend.partial
        ? t.spend.atLeast(f.money(spend.cost_usd))
        : f.money(spend.cost_usd),
      figures: [
        { key: "in", label: t.spend.tokensIn, value: f.plain(total.in, 0) },
        { key: "out", label: t.spend.tokensOut, value: f.plain(total.out, 0) },
        // Reported, and deliberately outside the arithmetic — Anthropic bills a
        // cached read at a discount this project has no sourced figure for, and a
        // guessed discount is a guess with a dollar sign in front of it.
        { key: "cache", label: t.spend.cached, value: f.plain(total.cache_read, 0),
          note: t.spend.cachedNote },
      ],
      models: models.map((m) => ({
        model: m.model,
        split: t.spend.split(f.plain(m.in, 0), f.plain(m.out, 0)),
        cost: priced(m.cost_usd),
        priced: m.cost_usd !== null,
      })),
      stray: strayTokens
        ? {
            model: t.spend.unattributed,
            split: t.spend.split(f.plain(unattributed.in, 0), f.plain(unattributed.out, 0)),
            cost: t.spend.noPrice,
            priced: false,
          }
        : null,
      unpriced: models.find((m) => m.cost_usd === null)?.model ?? null,
    };
  }, [spend, t, f]);
}
