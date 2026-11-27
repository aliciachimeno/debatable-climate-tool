"""Read a chapter's reference list from its indexed sentences, and match in-text citations to it.

The PDF reference list reaches us as sentences ("Author, A., ..., 2019: Title." then
"Journal, 11(3), 1189-1202, doi:10.5194/..."), with page headers glued onto some of them and
DOIs split across lines. Here we regroup them into one entry per reference.
"""
import re
import unicodedata
from dataclasses import asdict, dataclass

from .mentions import PARTICLES, NAME

# "382 Chapter 2\x08 Changing State of the Climate System 2 " and "381 Changing State ...\x08 Chapter 2 2 "
_PAGE_HEADER = re.compile(
    r"^\d{1,4}\s+(?:Chapter\s+\d+\x08\s+.*?\s+\d+\s+|[^\x08]*?\x08\s+Chapter\s+\d+\s+\d+\s+)")

_ENTRY = re.compile(
    rf"^(?P<author>{PARTICLES}{NAME}(?:\s{NAME})?),\s+"
    rf"(?:[A-ZÀ-Ý][\w\.\-\s,&'’À-ÿ]{{0,400}}?,?\s*)?"
    rf"(?P<year>(?:19|20)\d{{2}}[a-z]?):\s+(?P<title>.+)$", re.S)
# Two entries can end up in one sentence ("... doi:10.1007/x-4. Lee, J.-Y. and K.-J. Ha, 2015: ...")
_BOUNDARY = re.compile(
    rf"(?<=[a-z\d\)]\.)\s+(?={PARTICLES}{NAME}(?:\s{NAME})?,\s+"
    rf"(?:(?:[A-ZÀ-Ý]\.-?)+\s*[\w\.\-\s,&'’À-ÿ]{{0,400}}?,?\s*)?(?:19|20)\d{{2}}[a-z]?:\s)")
_INITIALS = re.compile(r"(?<![A-Za-z])(?:[A-Z]\.-?)+(?=[\s,]|$)")
_SECOND = re.compile(rf"\band\s+(?:(?:[A-Z]\.-?)+\s*)+(?P<s>{PARTICLES}{NAME})")
_DOI = re.compile(r"doi:\s*(10\.\d{4,9}/\S*)", re.I)
_LONE_INITIAL = re.compile(r"(?<![A-Za-z])[A-Z]\.$")


def strip_page_header(text: str) -> str:
    """Remove the running page header that PDF extraction glues onto the first sentence of a page."""
    if "\x08" in text[:140]:
        return _PAGE_HEADER.sub("", text, count=1)
    return text


def author_key(name: str) -> str:
    """'von Schuckmann' -> 'vonschuckmann': accents, case, spaces and hyphens do not matter."""
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", folded.lower())


@dataclass
class Reference:
    id: str
    idx: int                  # sentence index where the entry starts
    page: int
    author: str               # first author's surname (or organisation)
    year: str                 # with the a/b suffix when present
    raw: str
    title: str
    doi: str | None
    n_authors: int = 1        # 1, 2, or 3 for "three or more / et al."
    second: str = ""          # second author's surname when there are exactly two

    @property
    def key(self) -> str:
        return author_key(self.author)

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("doi", "second"):
            if not d[k]:
                del d[k]
        return d


_JOURNAL = re.compile(r"\.\s+(?=(?:In:|[A-Z][^.]{2,120}?,\s*\d+[\d()\w–-]*,))")


def _title(rest: str) -> str:
    """'Title. Journal, 121(13), 8125-8136, doi:...' -> 'Title.' (the whole text if no journal part is found)."""
    m = _JOURNAL.search(rest)
    return (rest[:m.start() + 1] if m else rest).strip()


def _authors(raw: str, year: str) -> tuple[int, str]:
    block = raw.split(f", {year}:", 1)[0] if f", {year}:" in raw else raw[:120]
    if "et al" in block:
        return 3, ""
    n = min(max(len(_INITIALS.findall(block)), 1), 3)
    second = _SECOND.search(block)
    return n, (second.group("s") if second and n == 2 else "")


def _finish(raw: str) -> tuple[str, str | None]:
    """Cut the entry after its (first) DOI and return (raw, doi). PDF extraction can leave a
    space inside a DOI ("10.1038/ nclimate2235", "10.1016/j. quascirev..."); rejoin those."""
    m = _DOI.search(raw)
    if not m:
        return raw, None
    doi, end = m.group(1), m.end()
    rest = raw[end:]
    while doi.endswith(("/", "-", "/j.")) and rest.startswith(" "):
        nxt = rest.split(None, 1)[0] if rest.strip() else ""
        doi, end = doi + nxt, end + 1 + len(nxt)
        rest = raw[end:]
    return raw[:end].strip(), doi.rstrip(".,;)")


def merge_fragments(rows: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """The sentence splitter cuts author lists after an initial ("Ahn, M." | "-S. et al., 2017: ...").
    A sentence that ends in a lone initial is not finished: join it with the next one."""
    out: list[tuple[int, int, str]] = []
    carry: tuple[int, int, str] | None = None
    for idx, page, text in rows:
        if carry:
            sep = "" if text.startswith("-") else " "
            idx, page, text = carry[0], carry[1], carry[2] + sep + text
            carry = None
        if _LONE_INITIAL.search(text) and len(text) < 400:
            carry = (idx, page, text)
        else:
            out.append((idx, page, text))
    if carry:
        out.append(carry)
    return out


def _entry_start(text: str):
    return _ENTRY.match(strip_page_header(text).removeprefix("References ").strip())


def find_reference_start(rows: list[tuple[int, int, str]]) -> int | None:
    """Sentence index where the reference list begins ('... 2 References Ablain, M. et al., 2019: ...')."""
    for idx, _, text in rows:
        body = strip_page_header(text)
        if body.startswith("References ") and _entry_start(body):
            return idx
    return None


def parse_references(rows: list[tuple[int, int, str]]) -> tuple[list[Reference], int | None]:
    """rows: (idx, page, text) in reading order. Returns the entries and where the list starts."""
    start = find_reference_start(rows)
    if start is None:
        return [], None
    entries: list[tuple[re.Match, int, int, list[str]]] = []
    for idx, page, text in merge_fragments([r for r in rows if r[0] >= start]):
        body = strip_page_header(text).removeprefix("References ").strip()
        for piece in _BOUNDARY.split(body):
            m = _ENTRY.match(piece)
            if m:
                entries.append((m, idx, page, [piece]))
            elif entries:
                entries[-1][3].append(piece)
    refs = []
    for n, (m, idx, page, parts) in enumerate(entries):
        raw, doi = _finish(" ".join(p for p in parts if p))
        n_authors, second = _authors(raw, m.group("year"))
        title = _ENTRY.match(raw)
        refs.append(Reference(f"r{n}", idx, page, m.group("author"), m.group("year"), raw,
                              _title((title or m).group("title")), doi, n_authors, second))
    return refs, start


class ReferenceTable:
    """Look up the reference a citation like ('Freeman', '2017') points to."""

    def __init__(self, refs: list[Reference]):
        self.refs = refs
        self._exact: dict[tuple[str, str], list[Reference]] = {}
        self._loose: dict[tuple[str, str], list[Reference]] = {}
        for r in refs:
            self._exact.setdefault((r.key, r.year), []).append(r)
            self._loose.setdefault((r.key, r.year[:4]), []).append(r)

    def match(self, author: str, year: str, n_authors: int | None = None,
              second: str = "") -> tuple[str, float, list[Reference]]:
        """(status, confidence, candidates). status: resolved | ambiguous | not_found.

        1.0 one entry for author + year (+ suffix); 0.9 several, told apart by the number of
        authors ("et al." / "A and B" / "A"); 0.8 / 0.7 the same when the year suffix is missing
        on one side; 0.5 still several (ambiguous: the candidates are returned)."""
        key = author_key(author)
        for pool, sure, narrowed in ((self._exact, 1.0, 0.9), (self._loose, 0.8, 0.7)):
            found = pool.get((key, year if pool is self._exact else year[:4]), [])
            if len(found) == 1:
                return "resolved", sure, found
            if found:
                pick = self._narrow(found, n_authors, second)
                if len(pick) == 1:
                    return "resolved", narrowed, pick
                return "ambiguous", 0.5, pick or found
        return "not_found", 0.0, []

    @staticmethod
    def _narrow(found: list[Reference], n_authors: int | None, second: str) -> list[Reference]:
        if n_authors is None:
            return found
        pick = [r for r in found if r.n_authors == n_authors]
        if n_authors == 2 and second and len(pick) > 1:
            pick = [r for r in pick if author_key(r.second) == author_key(second)] or pick
        return pick
