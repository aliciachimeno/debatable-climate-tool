from ..schemas import Finding, Window


def norm(s: str) -> str:
    return " ".join(s.lower().split())


def locate(quote: str, window: Window) -> list[int] | None:
    """Pages spanned by `quote` if it appears verbatim in the window, else None."""
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
    return sorted({window.sentences[i][0] for i in range(first, last + 1)})


def verify(raw_findings: list, windows: list[Window]) -> list[Finding]:
    """Keep only findings whose quote literally appears in the cited window."""
    by_id = {w.id: w for w in windows}
    good = []
    for f in raw_findings:
        if not isinstance(f, dict):
            continue
        w = by_id.get(f.get("passage_id"))
        quote, statement = str(f.get("quote", "")), str(f.get("statement", ""))
        pages = locate(quote, w) if w and statement else None
        if pages:
            good.append(Finding(statement, quote, w.doc, pages, w.id))
    return good