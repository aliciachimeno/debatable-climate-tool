"""Where things are inside a document: section ranges and figure / table / box captions.

Both are read from the indexed sentences. The table of contents tells us which headings are
real (a number like "2.2.1" at the start of a sentence is not enough on its own).
"""
import re
from collections import Counter

from .mentions import caption_label
from .references import strip_page_header

_TOC_ENTRY = re.compile(r"(?<![\d.])(\d+(?:\.\d+)+)\s+([A-Z][^\x08]*?)\s*\x08\s*\.{3,}")
# a heading can sit in the middle of a sentence (after a table, say), so look for it anywhere
_HEADING = re.compile(r"(?<![\w./-])(\d{1,2}(?:\.\d{1,2})+)\s+(?=[A-Z])")
_POINTER_BEFORE = re.compile(r"(?:Sections?|Chapters?|Figure|Table|Box|FAQ|and|in|of|see)\s+$")
_CAPTION = re.compile(
    r"(?:^|\s)(?P<kind>Cross-Chapter\s+Box|Box|Figure|Table|FAQ)\s+"
    r"(?P<num>(?:SPM|TS|ES|\d{1,2})\.\d+(?:\.\d+)*)(?:,\s*(?:Figure|Table)\s+\d+)?\s*\|\s*(?P<title>.+)$", re.S)
MAX_TITLE = 200
_SMALL = {"of", "and", "the", "in", "on", "to", "for", "from", "by", "with", "a", "an", "over", "under",
          "at", "as", "or", "vs", "during", "between", "since", "–", "-", "–"}


def guess_title(body: str, start: int, limit: int = 14) -> str:
    """A heading title read off the running text, only when it is clearly delimited: it must end
    at the next section number (headings that run together) and not at an ordinary word, because
    then we cannot tell where the title stops. Otherwise '' (the table of contents is the source)."""
    words = []
    for w in body[start:].split()[:limit]:
        if re.fullmatch(r"\d+(?:\.\d+)+", w):
            return " ".join(words)
        if not (w[0].isupper() or w[0] in "(0123456789" or w in _SMALL):
            return ""
        words.append(w)
    return ""


def _is_toc(text: str) -> bool:
    return "\x08" in text and "..." in text


def read_toc(rows: list[tuple[int, int, str]]) -> dict[str, str]:
    """{'2.2.1': 'Solar and Orbital Forcing'} from the table of contents pages."""
    toc: dict[str, str] = {}
    for _, _, text in rows:
        if _is_toc(text):
            for num, title in _TOC_ENTRY.findall(text):
                toc.setdefault(num, " ".join(title.split()))
    return toc


def find_sections(rows: list[tuple[int, int, str]], toc: dict[str, str] | None = None) -> dict[str, dict]:
    """{'2.2.1': {'title', 'lo', 'hi', 'page'}}: the sentence range each section covers.

    A number counts as a heading if it is in the table of contents, or if it is the next sibling
    in sequence (2.3.1.2 after 2.3.1.1) under a heading already seen, so a stray number in the
    text cannot pass. A section runs until the next heading of the same or a higher level."""
    toc = read_toc(rows) if toc is None else toc
    chapter = Counter(n.split(".")[0] for n in toc).most_common(1)
    chapter = chapter[0][0] if chapter else None
    heads: list[tuple[int, int, str, str]] = []        # (idx, page, number, guessed title), reading order
    seen: set[str] = set()
    last_child: dict[str, int] = {}
    for idx, page, text in rows:
        if _is_toc(text):
            continue
        body = strip_page_header(text)
        for m in _HEADING.finditer(body):
            num = m.group(1)
            if chapter and num.split(".")[0] != chapter or _POINTER_BEFORE.search(body[:m.start()]):
                continue
            parent, _, tail = num.rpartition(".")
            sequential = int(tail) == last_child.get(parent, 0) + 1 and (parent in seen or parent.count(".") == 0)
            if num in toc or sequential:
                heads.append((idx, page, num, guess_title(body, m.end())))
                seen.add(num)
                last_child[parent] = int(tail)
    last = rows[-1][0] if rows else 0
    out: dict[str, dict] = {}
    for i, (idx, page, num, guess) in enumerate(heads):
        level = num.count(".")
        hi = last
        for nxt_idx, _, nxt, _ in heads[i + 1:]:
            if nxt.count(".") <= level:
                hi = max(idx, nxt_idx - 1)
                break
        found = {"title": toc.get(num) or guess, "lo": idx, "hi": hi, "page": page}
        if num not in out or hi - idx > out[num]["hi"] - out[num]["lo"]:
            out[num] = found                           # a number can also appear in a "visual guide": keep the real one
    return out


def find_captions(rows: list[tuple[int, int, str]], stop: int | None = None) -> dict[str, dict]:
    """{'Figure 2.13': {'title', 'idx', 'page'}} for every 'Figure 2.13 | Title.' caption."""
    out: dict[str, dict] = {}
    for idx, page, text in rows:
        if stop is not None and idx >= stop:
            break
        m = _CAPTION.search(strip_page_header(text))
        if not m or _is_toc(text):
            continue
        _, label = caption_label(m.group("kind"), m.group("num"))
        title = " ".join(m.group("title").split())
        if "|" in title:                               # a table of contents inside a figure, not a caption
            continue
        title = re.split(r"\s+Contributing Authors:", title)[0]
        if len(title) > MAX_TITLE:
            title = title[:MAX_TITLE].rsplit(" ", 1)[0] + "…"
        out.setdefault(label, {"title": title, "idx": idx, "page": page})
    return out
