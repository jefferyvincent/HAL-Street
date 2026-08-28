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

/**
 * Every outcome `_pass` can reach for one name in a scan.
 *
 * Listed here rather than read off the payload so a state the server grows and this
 * build has never heard of falls back to its raw key instead of rendering blank —
 * `undefined` in a table cell is indistinguishable from a row that has not got there
 * yet, which is the one distinction this table exists to draw.
 */
/** The cycle's steps, mirroring `lib/pipeline`. */
export const STEP_KEYS = ["tape", "menu", "desk", "gates", "order"] as const;

export const OUTCOME_KEYS = ["running", "no menu", "passed", "proposed", "approved",
                             "rejected", "submitted", "error", "unfinished"] as const;

/** i18next's `t`, narrowed to what this file uses: a key, some named variables, a string back. */
export type Translate = (key: string, vars?: Record<string, unknown>) => string;

export function makeStrings(t: Translate) {
  return {
    // Glyphs and separators the panel joins things with. A locale that punctuates a
    // list differently changes it here, not in nine components.
    common: {
      dash: t("common.dash"),
      unknown: t("common.unknown"),
      listSep: t("common.listSep"),
      gateSep: t("common.gateSep"),
      sep: t("common.sep"),
      keySep: t("common.keySep"),
    },

    // The words the number formatters put around a figure. `amount` arrives already
    // formatted, so a translation reorders the sentence rather than being stuck
    // after it. See `lib/format.ts`, which takes this and holds no English of its own.
    format: {
      dash: t("common.dash"),
      credit: (amount: string) => t("format.credit", { amount }),
      debit: (amount: string) => t("format.debit", { amount }),
      toClose: (amount: string) => t("format.toClose", { amount }),
      justNow: t("format.justNow"),
      minutesAgo: (n: number) => t("format.minutesAgo", { n }),
      hoursAgo: (n: number) => t("format.hoursAgo", { n }),
      stamped: (day: string, clock: string) => t("format.stamped", { day, clock }),
    },

    app: {
      waiting: t("app.waiting"),
    },

    chrome: {
      brand: t("chrome.brand"),
      paper: t("chrome.paper"),
      armed: t("chrome.armed"),
      dryRun: t("chrome.dryRun"),
      armedUnknown: t("chrome.armedUnknown"),
      armedTitle: t("chrome.armedTitle"),
      dryRunTitle: t("chrome.dryRunTitle"),
      armedUnknownTitle: t("chrome.armedUnknownTitle"),
      busyTitle: t("chrome.busyTitle"),
      equity: t("chrome.equity"),
      breakerArmed: t("chrome.breakerArmed"),
      breakerHalted: t("chrome.breakerHalted"),
      soundOn: t("chrome.soundOn"),
      soundOff: t("chrome.soundOff"),
      soundArming: t("chrome.soundArming"),
      soundTitle: t("chrome.soundTitle"),
      marketOpen: t("chrome.marketOpen"),
      marketClosed: t("chrome.marketClosed"),
      marketUnknown: t("chrome.marketUnknown"),
      marketTitleOpen: (at: string) => t("chrome.marketTitleOpen", { at }),
      marketTitleClosed: (at: string) => t("chrome.marketTitleClosed", { at }),
      marketTitleUnknown: t("chrome.marketTitleUnknown"),
      marketTitleBoundary: (crossed: string) => t("chrome.marketTitleBoundary", { crossed }),
      marketTitlePublished: (until: string) =>
        t("chrome.marketTitlePublished", { until }),
      marketTitleLastSeen: (at: string) => t("chrome.marketTitleLastSeen", { at }),
    },

    periods: {
      title: t("periods.title"),
      realized: t("periods.realized"),
      marked: t("periods.marked"),
      label: {
        day: t("periods.label.day"),
        week: t("periods.label.week"),
        month: t("periods.label.month"),
        year: t("periods.label.year"),
        all: t("periods.label.all"),
      },
      closed: (count: number) => t("periods.closed", { count }),
      noneClosed: t("periods.noneClosed"),
      note: t("periods.note"),
      shortNote: (since: string) => t("periods.shortNote", { since }),
    },

    spend: {
      title: t("spend.title"),
      cycles: (count: number) => t("spend.cycles", { count }),
      tokensIn: t("spend.tokensIn"),
      tokensOut: t("spend.tokensOut"),
      cached: t("spend.cached"),
      cachedNote: t("spend.cachedNote"),
      split: (tin: string, out: string) => t("spend.split", { in: tin, out }),
      noPrice: t("spend.noPrice"),
      atLeast: (value: string) => t("spend.atLeast", { value }),
      noPriceNote: (model: string) => t("spend.noPriceNote", { model }),
      unattributed: t("spend.unattributed"),
      unattributedNote: t("spend.unattributedNote"),
    },

    discovery: {
      title: t("discovery.title"),
      meta: (symbols: number, headlines: number) =>
        t("discovery.meta", { symbols, headlines }),
      note: t("discovery.note"),
      emptyWaiting: t("discovery.emptyWaiting"),
      emptyNoCensus: t("discovery.emptyNoCensus"),
      legend: t("discovery.legend"),
      scanned: t("discovery.scanned"),
      refused: t("discovery.refused"),
      notReached: t("discovery.notReached"),
      scannedNote: t("discovery.scannedNote"),
      refusedNote: t("discovery.refusedNote"),
      notReachedNote: t("discovery.notReachedNote"),
      cellTitle: (symbol: string, mentions: number, headline: string) =>
        t("discovery.cellTitle", { symbol, mentions, headline }),
      cellRefused: (symbol: string, mentions: number, reason: string, headline: string) =>
        t("discovery.cellRefused", { symbol, mentions, reason, headline }),
      mentions: (n: number) => t("discovery.mentions", { n }),
      cut: (n: number) => t("discovery.cut", { n }),
      hottest: (n: number) => t("discovery.hottest", { n }),
    },

    presence: {
      disconnected: t("presence.disconnected"),
      closed: t("presence.closed"),
      closedUntil: (day: string, time: string) => t("presence.closedUntil", { day, time }),
      silent: t("presence.silent"),
      shortDisconnected: t("presence.shortDisconnected"),
      shortClosed: t("presence.shortClosed"),
      shortSilent: t("presence.shortSilent"),
      shortIdle: t("presence.shortIdle"),
      opensAt: (day: string, time: string) => t("presence.opensAt", { day, time }),
    },

    news: {
      label: t("news.label"),
      title: t("news.title"),
      age: (n: number) => t("news.age", { n }),
      read: (source: string) => t("news.read", { source }),
      wasRead: (roots: string, source: string) => t("news.wasRead", { roots, source }),
      fromCensus: (source: string) => t("news.fromCensus", { source }),
    },

    tabs: {
      console: t("tabs.console"),
      journal: t("tabs.journal"),
      discovery: t("tabs.discovery"),
      gates: t("tabs.gates"),
      committee: t("tabs.committee"),
      agent: t("tabs.agent"),
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

    scoreboard: {
      title: t("scoreboard.title"),
      realized: t("scoreboard.realized"),
      unrealized: t("scoreboard.unrealized"),
      total: t("scoreboard.total"),
      record: t("scoreboard.record"),
      recordValue: (wins: number, losses: number) =>
        t("scoreboard.recordValue", { wins, losses }),
      recordNone: t("scoreboard.recordNone"),
      rate: (pct: string, closed: number) => t("scoreboard.rate", { pct, closed }),
      equity: t("scoreboard.equity"),
      drawdown: t("scoreboard.drawdown"),
      drawdownNote: (samples: number) => t("scoreboard.drawdownNote", { samples }),
      turns: t("scoreboard.turns"),
      turnsValue: (proposals: number, passed: number) =>
        t("scoreboard.turnsValue", { proposals, passed }),
      turnsNote: t("scoreboard.turnsNote"),
      gated: t("scoreboard.gated"),
      gatedValue: (approved: number, rejected: number) =>
        t("scoreboard.gatedValue", { approved, rejected }),
      orders: t("scoreboard.orders"),
      unrealizedNote: t("scoreboard.unrealizedNote"),
      drawdownValue: (usd: string, pct: string) =>
        t("scoreboard.drawdownValue", { usd, pct }),
    },

    console: {
      activity: t("console.activity"),
      holding: t("console.holding"),
      open: t("console.open"),
      openTitle: t("console.openTitle"),
      expand: t("console.expand"),
      collapse: t("console.collapse"),
      openTrade: t("console.openTrade"),
      live: t("console.live"),
      partial: (count: number) => t("console.partial", { count }),
      holdingNone: t("console.holdingNone"),
      asOf: (when: string) => t("console.asOf", { when }),
      dte: (days: number) => t("console.dte", { days }),
      unpriced: t("console.unpriced"),
      none: t("console.none"),
      approved: (n: number) => t("console.approved", { n }),
      rejected: (bad: number, n: number) => t("console.rejected", { bad, n }),
      rationale: t("console.rationale"),
      rejectReasons: t("console.rejectReasons"),
      noOverride: t("console.noOverride"),
      confidence: (value: string) => t("console.confidence", { value }),
      confidenceNote: t("console.confidenceNote"),
      // The three figures above the ledger, labelled by the key `lib/decisions.ts`
      // gives them rather than by the key itself.
      qty: (qty: number) => t("console.qty", { qty }),
      facts: {
        net: t("console.factNet"),
        qty: t("console.factQty"),
        legs: t("console.factLegs"),
      } as Record<string, string>,
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
      gateCount: (passed: number, total: number) =>
        t("journal.gateCount", { passed, total }),
    },

    gates: {
      title: t("gates.title"),
      meta: (gates: number, seen: number) => t("gates.meta", { gates, seen }),
      rejectedCount: (n: number) => t("gates.rejectedCount", { n }),
      neverRejected: t("gates.neverRejected"),
      readAt: (structure: string, when: string) => t("gates.readAt", { structure, when }),
      readOnly: t("gates.readOnly"),
      afterHours: t("gates.afterHours"),
      limits: t("gates.limits"),
      limitsNote: t("gates.limitsNote"),
      note: (seen: number) => t("gates.note", { seen }),
      familyHeading: (family: string, count: number) =>
        t("gates.familyHeading", { family, count }),
    },

    committeeRail: {
      title: t("committeeRail.title"),
      gates: t("committeeRail.gates"),
      more: (count: number) => t("committeeRail.more", { count }),
      none: t("committeeRail.none"),
      elsewhere: (underlying: string, stage: string) =>
        t("committeeRail.elsewhere", { underlying, stage }),
    },

    hero: {
      equity: t("hero.equity"),
      today: t("hero.today"),
      unknown: t("hero.unknown"),
      target: {
        scan: t("hero.target.scan"),
        open: t("hero.target.open"),
        close: t("hero.target.close"),
      } as Record<string, string>,
      mins: t("hero.mins"),
      secs: t("hero.secs"),
      hours: t("hero.hours"),
      waiting: t("hero.waiting"),
      waitingNote: t("hero.waitingNote"),
      stats: (scans: number, gated: number, open: number, orders: number) =>
        t("hero.stats", { scans, gated, open, orders }),
    },

    agent: {
      title: t("agent.title"),
      meta: (done: number, count: number) => t("agent.meta", { done, count }),
      empty: t("agent.empty"),
      started: (ago: string) => t("agent.started", { ago }),
      spot: (price: string) => t("agent.spot", { price }),
      menuBuilt: (count: number) => t("agent.menuBuilt", { count }),
      menuNone: t("agent.menuNone"),
      rejectedBy: (gates: string) => t("agent.rejectedBy", { gates }),
      step: STEP_KEYS.reduce<Record<string, string>>((all, key) => {
        all[key] = t(`agent.step.${key}`);
        return all;
      }, {}),
      outcome: OUTCOME_KEYS.reduce<Record<string, string>>((all, key) => {
        all[key] = t(`agent.outcome.${key}`);
        return all;
      }, {}),
      read: (bias: string, regime: string, persistence: string) =>
        t("agent.read", { bias, regime, persistence }),
      reach: (days: number) => t("agent.reach", { days }),
      noRead: t("agent.noRead"),
      pulse: t("agent.pulse"),
      pulseNote: t("agent.pulseNote"),
    },

    committee: {
      title: t("committee.title"),
      meta: (count: number) => t("committee.meta", { count }),
      empty: t("committee.empty"),
      headlines: (count: number) => t("committee.headlines", { count }),
      catalyst: t("committee.catalyst"),
      bull: t("committee.bull"),
      bear: t("committee.bear"),
      judge: t("committee.judge"),
      brief: {
        title: t("committee.brief.title"),
        meta: (count: number) => t("committee.brief.meta", { count }),
        empty: t("committee.brief.empty"),
        waiting: t("committee.brief.waiting"),
        signal: (news: string, chart: string, agreement: string) =>
          t("committee.brief.signal", { news, chart, agreement }),
        noNews: t("committee.brief.noNews"),
        fit: {
          fits: t("committee.brief.fits"),
          against: t("committee.brief.against"),
          ambient: t("committee.brief.ambient"),
        } as Record<string, string>,
        unscored: t("committee.brief.unscored"),
        pop: (value: string) => t("committee.brief.pop", { value }),
        risk: (loss: string, gain: string) => t("committee.brief.risk", { loss, gain }),
        score: (value: string) => t("committee.brief.score", { value }),
        ev: (value: string) => t("committee.brief.ev", { value }),
        evNote: (cost: string) => t("committee.brief.evNote", { cost }),
        tail: (pct: string) => t("committee.brief.tail", { pct }),
        unsimulated: t("committee.brief.unsimulated"),
        scenarioNote: (paths: string, note: string) =>
          t("committee.brief.scenarioNote", { paths, note }),
        persistence: (label: string, state: string, repeats: string, base: string) =>
          t("committee.brief.persistence", { label, state, repeats, base }),
        reach: (days: number) => t("committee.brief.reach", { days }),
        outOfReach: t("committee.brief.outOfReach"),
        note: t("committee.brief.note"),
      },
      desk: {
        title: t("committee.desk.title"),
        live: t("committee.desk.live"),
        progress: (pct: string, elapsed: string) =>
          t("committee.desk.progress", { pct, elapsed }),
        idle: t("committee.desk.idle"),
        idleDetail: (ago: string) => t("committee.desk.idleDetail", { ago }),
        idleNever: t("committee.desk.idleNever"),
        closed: t("committee.desk.closed"),
        silent: t("committee.desk.silent"),
        silentDetail: t("committee.desk.silentDetail"),
        offline: t("committee.desk.offline"),
        offlineDetail: t("committee.desk.offlineDetail"),
        archived: (count: number) => t("committee.desk.archived", { count }),
        empty: t("committee.desk.empty"),
        catalyst: t("committee.desk.catalyst"),
        bull: t("committee.desk.bull"),
        bear: t("committee.desk.bear"),
        debate: t("committee.desk.debate"),
        judge: t("committee.desk.judge"),
        gates: t("committee.desk.gates"),
        in: t("committee.desk.in"),
        working: t("committee.desk.working"),
        pending: t("committee.desk.pending"),
        absent: t("committee.desk.absent"),
        skipped: t("committee.desk.skipped"),
        read: (lean: string, value: string) =>
          t("committee.desk.read", { lean, value }),
        note: t("committee.desk.note"),
        clipped: t("committee.desk.clipped"),
        archiveShow: (count: number) => t("committee.desk.archiveShow", { count }),
        archiveHide: t("committee.desk.archiveHide"),
        archiveNote: t("committee.desk.archiveNote"),
      },
      railScan: (count: number) => t("committee.railScan", { count }),
      railNoneFresh: (count: number) => t("committee.railNoneFresh", { count }),
      reflection: t("committee.reflection"),
      reflectionEmpty: t("committee.reflectionEmpty"),
      missing: t("committee.missing"),
      silent: t("committee.silent"),
      passed: t("committee.passed"),
      proposed: t("committee.proposed"),
      failed: t("committee.failed"),
      approved: t("committee.approved"),
      rejected: (gates: string) => t("committee.rejected", { gates }),
      ungated: t("committee.ungated"),
      confidence: (value: string) => t("committee.confidence", { value }),
      tokens: (out: number) => t("committee.tokens", { out }),
      note: t("committee.note"),
      latest: t("committee.latest"),
      working: (stage: string, underlying: string) =>
        t("committee.working", { stage, underlying }),
      workingAny: t("committee.workingAny"),
      waiting: t("committee.waiting"),
      ordered: t("committee.ordered"),
      cost: t("committee.cost"),
      costNote: t("committee.costNote"),
      // The catalyst's own word, translated where we know it and shown as it came
      // where we do not — it is model output, not a fixed set.
      lean: {
        bullish: t("committee.lean.bullish"),
        bearish: t("committee.lean.bearish"),
        neutral: t("committee.lean.neutral"),
      } as Record<string, string>,
      reflectionRow: (structure: string, realized: string, outcome: string) =>
        t("committee.reflectionRow", { structure, realized, outcome }),
      stageSpend: (tin: string, out: string) => t("committee.stageSpend", { in: tin, out }),
      stageModel: (model: string) => t("committee.stageModel", { model }),
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
      unrealizedTag: t("book.unrealizedTag"),
      unpriced: t("book.unpriced"),
      note: t("book.note"),
      exposure: {
        bullish: t("book.exposure.bullish"),
        bearish: t("book.exposure.bearish"),
        neutral: t("book.exposure.neutral"),
        unknown: t("book.exposure.unknown"),
      },
      // Chosen here rather than through i18next's plural machinery, which needs a
      // per-language rule set configured to work and fails silently to the singular
      // when it is not. Two keys and a comparison cannot fail silently.
      against: (count: number) =>
        count === 1 ? t("book.against") : t("book.againstMany", { count }),
      confirming: (count: number) =>
        count === 1 ? t("book.confirming") : t("book.confirmingMany", { count }),
      patternsNone: t("book.patternsNone"),
      patternsTitle: (underlying: string) => t("book.patternsTitle", { underlying }),
      patternLine: (name: string, note: string) => t("book.patternLine", { name, note }),
    },

    chart: {
      back: t("chart.back"),
      loading: t("chart.loading"),
      loadingNote: t("chart.loadingNote"),
      noHistory: t("chart.noHistory"),
      noEntry: t("chart.noEntry"),
      entry: t("chart.entry"),
      target: t("chart.target"),
      stop: t("chart.stop"),
      last: t("chart.last"),
      pnl: t("chart.pnl"),
      liveTag: t("chart.liveTag"),
      // The label on the chart's own price axis, drawn by lightweight-charts
      // rather than by any markup here — which is exactly why it needs saying.
      livePriceLine: t("chart.livePriceLine"),
      barTag: t("chart.barTag"),
      seriesNote: t("chart.seriesNote"),
      forming: t("chart.forming"),
      auto: t("chart.auto"),
      timeframeTitle: t("chart.timeframeTitle"),
      fitPrice: t("chart.fitPrice"),
      fitLevels: t("chart.fitLevels"),
      fitTitle: t("chart.fitTitle"),
      offscreen: (name: string, value: string) => t("chart.offscreen", { name, value }),
      legend: (tp: string, sl: string) => t("chart.legend", { tp, sl }),
      credit: t("chart.credit"),
      debit: t("chart.debit"),
      note: t("chart.note"),
      forceClose: (dte: number) => t("chart.forceClose", { dte }),
      legs: t("chart.legs"),
      legQty: t("chart.legQty"),
      legContract: t("chart.legContract"),
      legFill: t("chart.legFill"),
      legNow: t("chart.legNow"),
      exitAt: t("chart.exitAt"),
      legPnl: t("chart.legPnl"),
      legNoQuote: t("chart.legNoQuote"),
      legNoBasis: t("chart.legNoBasis"),
      legsNote: t("chart.legsNote"),
      legsPending: t("chart.legsPending"),
      legShort: t("chart.legShort"),
      legLong: t("chart.legLong"),
      openedAt: (day: string, time: string) => t("chart.openedAt", { day, time }),
      closedAt: (day: string, time: string) => t("chart.closedAt", { day, time }),
      dteTag: (days: number) => t("chart.dteTag", { days }),
      realizedTag: t("chart.realizedTag"),
      stopUnreachable: t("chart.stopUnreachable"),
      unreachableNote: t("chart.unreachableNote"),
    },

    tape: {
      viewTrade: t("tape.viewTrade"),
      title: t("tape.title"),
      empty: t("tape.empty"),
      counts: (approved: number, rejected: number, passed: number) =>
        t("tape.counts", { approved, rejected, passed }),
      approved: (n: number) => t("tape.approved", { n }),
      rejected: (bad: number, n: number) => t("tape.rejected", { bad, n }),
      dryRun: t("tape.dryRun"),
      dryRunTitle: t("tape.dryRunTitle"),
      earlier: (count: number) => t("tape.earlier", { count }),
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
      meterEntry: (family: string, count: number) =>
        t("status.meterEntry", { family, count }),
    },
  };
}

export type Strings = ReturnType<typeof makeStrings>;

export { DEFAULT_LOCALE, LOCALES, type Locale } from "@/locales";
