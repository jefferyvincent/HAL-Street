"""The one piece of untrusted input a browser will execute rather than display.

Headlines are publisher text and the panel renders them as text — React escapes them
and nothing is interpreted. A URL is different in kind: it goes into an `href` the
reader clicks, and `javascript:` in an anchor runs on click. That makes this the one
field in the system where "render it as data" is not enough.

So it is an allowlist, not a scrub, and it is applied once — on the server, with these
tests. The panel renders what comes back and adds no check of its own, because a
security control implemented in two places is one implemented in whichever place
somebody forgets.
"""

from __future__ import annotations

import pytest

from halstreet.marketdata.news import LINK_SCHEMES, MAX_URL, Headline, parse, safe_url

# --- what is allowed ------------------------------------------------------------

def test_a_real_article_link_survives_unchanged():
    url = ("https://www.benzinga.com/government/26/08/61479424/"
           "us-bank-regulators-narrow-enforcement-focus-financial-risks-financial-times")
    assert safe_url(url) == url


def test_plain_http_is_allowed():
    """An external link, not a request this process makes. Refusing it would drop
    real articles to protect against nothing."""
    assert safe_url("http://example.com/story") == "http://example.com/story"


def test_the_scheme_may_be_shouted():
    assert safe_url("HTTPS://A.COM/x") == "HTTPS://A.COM/x"


def test_query_strings_and_fragments_survive():
    url = "https://a.com/p?utm_source=x&id=7#top"
    assert safe_url(url) == url


# --- what is not ----------------------------------------------------------------

@pytest.mark.parametrize("attack", [
    "javascript:alert(1)",
    "JavaScript:alert(1)",
    "  javascript:alert(1)  ",
    # `urlsplit` removes tab, newline and carriage return before reading the scheme,
    # exactly as a browser does — so these arrive with a scheme of "javascript" and
    # are refused for being javascript, not for containing a tab. Here because they
    # are the classic bypass, and because they prove the allowlist is doing the work:
    # swap it for a blocklist and the ftp case below is what breaks first.
    "java\tscript:alert(1)",
    "java\nscript:alert(1)",
    "java\rscript:alert(1)",
    "jav\x00ascript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
    "vbscript:msgbox(1)",
    "file:///etc/passwd",
    "ftp://host/x",
    "about:blank",
    "blob:https://a.com/uuid",
])
def test_anything_outside_the_allowlist_is_refused(attack):
    assert safe_url(attack) == ""


@pytest.mark.parametrize("bad", [None, "", "   ", 0, [], {}, "not a url", "https://",
                                 "//protocol-relative.example", "/relative/path"])
def test_what_is_not_a_link_yields_nothing(bad):
    assert safe_url(bad) == ""


def test_a_scheme_with_no_host_is_refused():
    """`https:alert(1)` parses with the right scheme and no netloc — an anchor to
    nowhere at best."""
    assert safe_url("https:alert(1)") == ""


def test_an_absurdly_long_url_is_refused():
    assert safe_url("https://a.com/" + "x" * MAX_URL) == ""
    assert safe_url("https://a.com/" + "x" * 10) != ""


def test_the_allowlist_is_an_allowlist():
    """Named schemes, not a list of the attacks someone happened to think of.

    This is the control, and `test_anything_outside_the_allowlist_is_refused` is what
    proves it: turn it into a blocklist and the `ftp://` case fails immediately, along
    with `about:`, `blob:` and everything nobody has thought of yet.
    """
    assert set(LINK_SCHEMES) == {"https", "http"}


def test_it_never_raises_on_a_shape_it_dislikes():
    """News is an enrichment, not a dependency. Everything in this module answers
    rather than throws, because a news problem must never become a trading problem."""
    for value in (object(), b"https://a.com", 3.14, [1, 2], {"url": "x"}):
        assert isinstance(safe_url(value), str)


# --- through the parser and onto the wire ---------------------------------------

def test_a_parsed_headline_carries_a_validated_link():
    (h,) = parse({"news": [{"headline": "Fed holds", "source": "wire",
                            "created_at": "2026-08-27T16:00:00Z",
                            "url": "https://a.com/fed"}]})
    assert h.url == "https://a.com/fed"
    assert h.to_ticker()["url"] == "https://a.com/fed"


def test_a_headline_with_a_hostile_link_still_reaches_the_reader():
    """The article is not the problem; the anchor is. Dropping the headline would let
    a bad URL suppress news the catalyst read, which is the wrong trade."""
    (h,) = parse({"news": [{"headline": "Fed holds", "source": "wire",
                            "created_at": "2026-08-27T16:00:00Z",
                            "url": "javascript:alert(1)"}]})
    assert h.headline == "Fed holds"
    assert h.url == "", "no link, and the panel renders it as plain text"


def test_a_headline_with_no_link_is_not_a_failure():
    (h,) = parse({"news": [{"headline": "Fed holds", "source": "wire",
                            "created_at": "2026-08-27T16:00:00Z"}]})
    assert h.url == ""


def test_the_default_is_no_link():
    """A Headline built anywhere else starts with nothing to click."""
    assert Headline(ts="", headline="h", source="s").url == ""


def test_the_panel_adds_no_check_of_its_own():
    """Deliberate, and worth pinning: a control implemented in two places is one
    implemented in whichever place someone forgets. This is the single place."""
    from pathlib import Path

    ticker = Path("apps/desktop/src/components/NewsTicker.tsx").read_text()
    assert "javascript" not in ticker.lower(), "the allowlist lives on the server"
    # What it does do: never hand the opened page a handle back to this one.
    assert 'rel="noopener noreferrer"' in ticker
    assert 'target="_blank"' in ticker
