import re

from ..schemas import Finding, Window
from .strength import strength
from ..schemas import STANCES, Finding, Window

MAX_QUOTE_WORDS = 40
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def norm(s: str) -> str:
    return " ".join(s.lower().split())


def _span(quote: str, window: Window) -> tuple[int, int] | None:
    """Positions (first, last) in window.sentences of the sentences `quote` spans, or None."""
    q = norm(quote)
    if not q:
        return None
    sents = [norm(t) for _, t in window.sentences]
    starts, pos = [], 0
    for s in sents:
        starts.append(pos)
        pos += len(s) + 1
    at = " ".join(sents).find(q)
    if at < 0:
        return None
    end = at + len(q) - 1
    first = max(i for i, s in enumerate(starts) if s <= at)
    last = max(i for i, s in enumerate(starts) if s <= end)
    return first, last


def locate(quote: str, window: Window) -> list[int] | None:
    """Pages spanned by `quote` if it appears verbatim in the window, else None."""
    span = _span(quote, window)
    if span is None:
        return None
    return sorted({window.sentences[i][0] for i in range(span[0], span[1] + 1)})


def locate_span(quote: str, window: Window) -> list[int] | None:
    """[first, last] sentence index (in the document) of the quote, or None."""
    span = _span(quote, window)
    return None if span is None else [window.lo + span[0], window.lo + span[1]]


def numbers_supported(statement: str, quote: str) -> bool:
    """Every number in the statement must also appear in the quote (catches paraphrase drift)."""
    in_quote = set(_NUMBER.findall(quote))
    return all(n in in_quote for n in _NUMBER.findall(statement))


def verify(raw_findings: list, windows: list[Window]) -> list[Finding]:
    """Keep only findings whose quote literally appears in the cited window,
    is short enough, and whose statement adds no numbers the quote lacks."""
    by_id = {w.id: w for w in windows}
    good = []
    for f in raw_findings:
        if not isinstance(f, dict):
            continue
        w = by_id.get(f.get("passage_id"))
        quote, statement = str(f.get("quote", "")), str(f.get("statement", ""))
        if not (w and statement) or len(quote.split()) > MAX_QUOTE_WORDS:
            continue
        if not numbers_supported(statement, quote):
            continue
        pages = locate(quote, w)
        if pages:
            stance = f.get("stance") if f.get("stance") in STANCES else None
            good.append(Finding(statement, quote, w.doc, pages, w.id, **strength(quote), stance=stance,
                                span=locate_span(quote, w)))
    return good
