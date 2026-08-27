/**
 * Every word the panel shows, in one place.
 *
 * Nothing in `views/` or `components/` contains a user-facing literal — they read
 * from here through `useStrings()`. The words themselves now live in `locales/*.json`
 * and are resolved by i18next, so translation is a matter of adding a sibling to
 * `en.json` rather than hunting through JSX. This file is the other half of that:
 * the typed shape the components see, and the single map from key to accessor.
 *
 * That map is worth keeping readable, because the panel's claims are all in it. The
 * sentences that say what this thing will not do — no override, no editable limit,
 * exits are never blocked — are load-bearing, and they should be reviewable together
 * rather than scattered across nine components.
 *
 * Anything with a number in it is a function taking named variables, so a translation
 * can reorder the sentence around it instead of being forced into English word order.
 */

import { FAMILY_KEYS } from "@/locales";

/** i18next's `t`, narrowed to what this file uses: a key, some named variables, a string back. */
export type Translate = (key: string, vars?: Record<string, unknown>) => string;

export function makeStrings(t: Translate) {
  return {
    app: {
      waiting: t("app.waiting"),
    },

    chrome: {
      brand: t("chrome.brand"),
      paper: t("chrome.paper"),
      equity: t("chrome.equity"),
      breakerArmed: t("chrome.breakerArmed"),
      breakerHalted: t("chrome.breakerHalted"),
      soundOn: t("chrome.soundOn"),
      soundOff: t("chrome.soundOff"),
      soundTitle: t("chrome.soundTitle"),
      marketOpen: t("chrome.marketOpen"),
      marketClosed: t("chrome.marketClosed"),
      marketUnknown: t("chrome.marketUnknown"),
    },

    tabs: {
      console: t("tabs.console"),
      journal: t("tabs.journal"),
      gates: t("tabs.gates"),
      book: t("tabs.book"),
    },

    // Keyed by whatever the server calls the family, so this is a lookup rather than
    // a fixed set of fields; callers fall back to the raw key for one they don't know.
    families: Object.fromEntries(
      FAMILY_KEYS.map((key) => [key, t(`families.${key}`)]),
    ) as Record<string, string>,

    halt: {
      tag: t("halt.tag"),
      detail: (reason: string) => t("halt.detail", { reason }),
    },

    console: {
      none: t("console.none"),
      approved: (n: number) => t("console.approved", { n }),
      rejected: (bad: number, n: number) => t("console.rejected", { bad, n }),
      rationale: t("console.rationale"),
      rejectReasons: t("console.rejectReasons"),
      noOverride: t("console.noOverride"),
      confidence: (value: string) => t("console.confidence", { value }),
      confidenceNote: t("console.confidenceNote"),
    },

    ledger: {
      allRan: (n: number) => t("ledger.allRan", { n }),
    },

    journal: {
      title: t("journal.title"),
      meta: (n: number) => t("journal.meta", { n }),
      empty: t("journal.empty"),
      columns: {
        time: t("journal.columns.time"),
        verdict: t("journal.columns.verdict"),
        underlying: t("journal.columns.underlying"),
        structure: t("journal.columns.structure"),
        gates: t("journal.columns.gates"),
        failedOn: t("journal.columns.failedOn"),
      },
      approved: t("journal.approved"),
      rejected: t("journal.rejected"),
      note: t("journal.note"),
    },

    gates: {
      title: t("gates.title"),
      meta: (gates: number, seen: number) => t("gates.meta", { gates, seen }),
      rejectedCount: (n: number) => t("gates.rejectedCount", { n }),
      neverRejected: t("gates.neverRejected"),
      note: (seen: number) => t("gates.note", { seen }),
    },

    book: {
      title: t("book.title"),
      meta: (open: number, closed: number) => t("book.meta", { open, closed }),
      empty: t("book.empty"),
      columns: {
        status: t("book.columns.status"),
        structure: t("book.columns.structure"),
        underlying: t("book.columns.underlying"),
        qty: t("book.columns.qty"),
        entry: t("book.columns.entry"),
        exit: t("book.columns.exit"),
        realized: t("book.columns.realized"),
      },
      open: t("book.open"),
      closed: t("book.closed"),
      note: t("book.note"),
      exposure: {
        bullish: t("book.exposure.bullish"),
        bearish: t("book.exposure.bearish"),
        neutral: t("book.exposure.neutral"),
        unknown: t("book.exposure.unknown"),
      },
      against: (count: number) => t("book.against", { count }),
      confirming: (count: number) => t("book.confirming", { count }),
      patternsNone: t("book.patternsNone"),
      patternsTitle: (underlying: string) => t("book.patternsTitle", { underlying }),
    },

    chart: {
      back: t("chart.back"),
      loading: t("chart.loading"),
      noHistory: t("chart.noHistory"),
      noEntry: t("chart.noEntry"),
      entry: t("chart.entry"),
      target: t("chart.target"),
      stop: t("chart.stop"),
      last: t("chart.last"),
      legend: (tp: string, sl: string) => t("chart.legend", { tp, sl }),
      credit: t("chart.credit"),
      debit: t("chart.debit"),
      note: t("chart.note"),
      forceClose: (dte: number) => t("chart.forceClose", { dte }),
    },

  rail: {
      families: t("rail.families"),
      limits: t("rail.limits"),
      limitsNote: t("rail.limitsNote"),
    },

    tape: {
      title: t("tape.title"),
      empty: t("tape.empty"),
      counts: (approved: number, rejected: number, passed: number) =>
        t("tape.counts", { approved, rejected, passed }),
      approved: (n: number) => t("tape.approved", { n }),
      rejected: (bad: number, n: number) => t("tape.rejected", { bad, n }),
    },

    equity: {
      title: t("equity.title"),
      none: t("equity.none"),
      one: t("equity.one"),
      scans: (n: number) => t("equity.scans", { n }),
      drawdown: (usd: string, pct: string) => t("equity.drawdown", { usd, pct }),
    },

    status: {
      prev: t("status.prev"),
      next: t("status.next"),
      latest: t("status.latest"),
      view: t("status.view"),
      updated: t("status.updated"),
      live: (gates: number) => t("status.live", { gates }),
      polling: (gates: number) => t("status.polling", { gates }),
      // Two sentences rather than one with an optional tail: a translation may not
      // be able to append the reason with a dash.
      disconnected: (why: string | null) =>
        why ? t("status.disconnectedWhy", { why }) : t("status.disconnected"),
    },
  };
}

export type Strings = ReturnType<typeof makeStrings>;

export { DEFAULT_LOCALE, LOCALES, type Locale } from "@/locales";
