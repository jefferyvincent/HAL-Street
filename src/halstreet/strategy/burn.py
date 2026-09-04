"""Every structure family tried against the news, before the committee argues.

The judge used to get a ranked menu and a catalyst's paragraph, and had to do two
jobs at once: decide what the news implies about direction, and decide which
structure expresses that. Only the first of those needs a model. A put credit spread
wants the tape up or flat, a call credit spread wants it down or flat, a condor wants
it still — that is true on every day of every year, and re-deriving it four model
calls at a time is paying for arithmetic.

So this module runs the mechanical half and hands the committee a comparison instead
of a list: the best candidate of each family, whether the news points its way, and —
the part that earns its keep — where the news and the chart disagree.

**Nothing here decides anything.** No structure is chosen, none is removed, and the
ranking is untouched. `Row.fit` is an annotation on a menu the model still picks
from, and the sixteen gates still hold the actual boundary. The change is that the
judge now argues against a table it can check rather than an intuition it has to
form on the spot.

**The conflict case is the point.** A bearish catalyst read against a bullish price
trend is not a bearish signal with a discount applied — it is two signals that cannot
both be right, and any directional structure built on it is picking one of them with
money. The deterministic answer is that neither has earned a direction, and `signal`
says so rather than quietly scoring one a little higher.

**One definition of direction, not two.** `scoring.bias_fit` has scored structure
against direction since before the committee existed, and it is what ranks the menu.
This module restates it in words rather than recomputing it: `fit` is derived from
`STRUCTURE_BIAS`, the same table, and a test pins the two together. A second opinion
here would mean the menu is ranked on one view of direction and argued on another.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from halstreet.strategy import profiles as P
from halstreet.strategy.bias import BEARISH, BULLISH, NEUTRAL
from halstreet.strategy.scoring import STRUCTURE_BIAS

#: Below this the catalyst's lean is discarded rather than downweighted.
#:
#: Its own system prompt says a confident read on a slow news day is worth less than
#: an honest shrug, and it is asked for confidence separately for exactly this reason.
#: A 0.1-confidence "bearish" carries no more information than silence; letting it
#: swing a structure family means the news moves the trade on the days it has nothing
#: to say, which is most days.
MIN_CONFIDENCE = 0.35

# How the two reads line up. Recorded and shown, never used to size anything.
CONFIRMED = "confirmed"        # news and chart point the same way
UNCONFIRMED = "unconfirmed"    # one speaks, the other is flat
CONFLICTED = "conflicted"      # they point opposite ways — no direction is earned
NO_NEWS = "no-news"            # the catalyst did not answer; the chart stands alone

# How a structure family sits against the combined read.
FITS = "fits"          # profits in the direction the read points
AGAINST = "against"    # needs the opposite of what the read says
AMBIENT = "ambient"    # the read has no opinion about this family either way

_NOTES = {
    CONFIRMED: "The news read and the price trend agree. A directional structure is "
               "backed by both.",
    UNCONFIRMED: "Only one of the news read and the price trend has a direction. The "
                 "other is flat, so the direction is unconfirmed rather than opposed.",
    CONFLICTED: "The news read and the price trend disagree. Neither direction has "
                "been earned, and a directional structure here is a bet on which of "
                "two contradictory signals is right.",
    NO_NEWS: "No catalyst read was available this cycle. The direction below is the "
             "price trend alone, with nothing from the tape to confirm it.",
}


@dataclass(frozen=True)
class Signal:
    """The two reads, and what they amount to together."""

    direction: str
    agreement: str
    #: The catalyst's lean as given, before the confidence floor. Kept so the record
    #: shows what was said and not only what was used.
    news: str | None = None
    chart: str = NEUTRAL
    confidence: float = 0.0

    @property
    def note(self) -> str:
        return _NOTES[self.agreement]


@dataclass(frozen=True)
class Row:
    """One structure family, tried against one read.

    The `signal` is carried on the row rather than returned alongside the table
    because a fit without the read that produced it is unfalsifiable — "this condor
    fits" means nothing until you can see what it was judged against. Every row in a
    table shares the same signal; keeping it here means the two cannot be separated
    on the way to the prompt.
    """

    kind: str
    fit: str
    why: str
    signal: Signal
    #: The best-scoring candidate of this family, or None when the chain offered none.
    candidate: Any | None = None


def signal(*, news: str | None, confidence: float, chart: str) -> Signal:
    """Combine the catalyst's read with the price trend into one direction.

    Deliberately not an average. Two directional signals that disagree do not produce
    a weak version of either — they produce the honest answer that no direction has
    been established, which is what a condor is for.
    """
    lean = news if news in (BULLISH, BEARISH, NEUTRAL) else None
    used = lean if (lean is not None and confidence >= MIN_CONFIDENCE) else NEUTRAL

    if lean is None:
        return Signal(direction=chart, agreement=NO_NEWS, news=news,
                      chart=chart, confidence=confidence)
    if used != NEUTRAL and chart != NEUTRAL:
        if used == chart:
            return Signal(direction=used, agreement=CONFIRMED, news=news,
                          chart=chart, confidence=confidence)
        return Signal(direction=NEUTRAL, agreement=CONFLICTED, news=news,
                      chart=chart, confidence=confidence)
    # One of the two is flat (or the read was too faint to count): the other stands,
    # unconfirmed. When both are flat that direction is NEUTRAL, which is a real read.
    return Signal(direction=used if used != NEUTRAL else chart, agreement=UNCONFIRMED,
                  news=news, chart=chart, confidence=confidence)


def _fit(kind: str, direction: str) -> tuple[str, str]:
    """Where one family sits against a direction, and why. Mirrors `scoring.bias_fit`."""
    wants = STRUCTURE_BIAS.get(kind)
    if wants is None:
        return AMBIENT, f"{kind} has no direction of its own"
    if direction == NEUTRAL:
        if wants == NEUTRAL:
            return FITS, ("no direction has been established, which is the condition "
                          "this structure is paid for")
        return AMBIENT, (f"wants the tape {_needs(wants)}; no direction has been "
                         "established either way")
    if wants == NEUTRAL:
        return AMBIENT, (f"wants the tape still, and the read is {direction}. One wing "
                         "does the work; it is not disqualified, and it is not what "
                         "you would choose")
    if wants == direction:
        return FITS, f"profits while the tape {_moves(wants)}, and the read is {direction}"
    return AGAINST, (f"needs the tape {_needs(wants)}, and the read is {direction} — "
                     "this structure is short the news")


def _moves(wants: str) -> str:
    """The clause that follows "profits while the tape ..."."""
    return "does not fall" if wants == BULLISH else "does not rally"


def _needs(wants: str) -> str:
    """The same fact after "needs the tape ..." / "wants the tape ...".

    A second form rather than a second phrasing of the sentence, because the first
    live run produced "needs the tape does not fall and the read is bearish" — one
    string used in a slot that wanted the infinitive. These strings are read by three
    models and by whoever reads the journal afterwards.
    """
    return "not to fall" if wants == BULLISH else "not to rally"


def table(candidates: list[Any], *, signal: Signal,
          families: tuple[str, ...] = P.VERTICALS_AND_CONDORS) -> list[Row]:
    """The best of each family, annotated with how it sits against the read.

    Every family gets a row even when the chain built none of it. "The market offered
    no condor here" and "a condor was never considered" are different facts and a
    judge reading a short table cannot tell them apart — one is the market's answer,
    the other is a bug in the builder.

    Ordered fits-first then by score, with the families that produced nothing last.
    Ordering is presentation only; the ranking the model chooses from is untouched.
    """
    best: dict[str, Any] = {}
    for c in candidates:
        kind = getattr(c, "kind", None)
        if kind not in families:
            continue
        if kind not in best or c.score > best[kind].score:
            best[kind] = c

    rows = []
    for kind in families:
        fit, why = _fit(kind, signal.direction)
        candidate = best.get(kind)
        rows.append(Row(kind=kind, fit=fit, candidate=candidate, signal=signal,
                        why=why if candidate is not None
                        else "the chain offered no candidate of this kind"))

    order = {FITS: 0, AMBIENT: 1, AGAINST: 2}
    return sorted(rows, key=lambda r: (r.candidate is None, order[r.fit],
                                       -float(r.candidate.score if r.candidate else 0)))


def to_prompt(rows: list[Row]) -> dict[str, Any]:
    """The table as the committee sees it. JSON-safe — it is embedded with `dumps`."""
    sig = rows[0].signal if rows else None
    out: dict[str, Any] = {
        "structures": [
            {
                "kind": r.kind,
                "news_fit": r.fit,
                "why": r.why,
                **({"name": r.candidate.name,
                    "net_price": str(r.candidate.net),
                    "max_loss_usd": str(r.candidate.max_loss_usd),
                    "max_gain_usd": str(r.candidate.max_gain_usd),
                    "prob_of_profit": (None if r.candidate.pop is None
                                       else round(r.candidate.pop, 3)),
                    "score": str(r.candidate.score)}
                   if r.candidate is not None else {"available": False}),
            }
            for r in rows
        ],
    }
    if sig is not None:
        out |= {"direction": sig.direction, "agreement": sig.agreement,
                "news_lean": sig.news, "price_trend": sig.chart,
                "news_confidence": round(sig.confidence, 2), "note": sig.note}
    return out
