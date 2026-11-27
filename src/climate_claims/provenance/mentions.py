"""Find the places a sentence points to: papers, other assessments, sections, figures, tables, boxes.

Detection only. Nothing here knows which documents are indexed; `resolve.py` turns a mention into
a link. Every form is one entry in a small pattern set, so a new form is a new pattern, not a new
parser. A mention that cannot be resolved is still kept (its status says why), so the failures
stay visible in the coverage report.
"""
import re
from dataclasses import dataclass, field

PARTICLES = r"(?:(?:de|van|von|der|den|la|le|di|da|dos|del|ten|ter|el|al)\s+)*"
NAME = r"[A-ZÀ-Ý][\wÀ-ÿ'’\-]+"
AUTHORS = rf"(?P<author>{PARTICLES}{NAME})(?:\s+et\s+al\.?|\s+(?:and|&)\s+{PARTICLES}{NAME})?"
YEAR = r"(?:19|20)\d{2}[a-z]?"
YEARS = rf"(?P<years>{YEAR}(?:\s*,\s*{YEAR})*)"

_PAREN = re.compile(r"\(([^()]*?\b(?:19|20)\d{2}[a-z]?[^()]*?)\)")
_CITE = re.compile(rf"{AUTHORS},?\s+{YEARS}")
_NARRATIVE = re.compile(rf"{AUTHORS}\s+\({YEARS}\)")
_YEAR = re.compile(YEAR)

_SECTION = re.compile(r"\bSections?\s+(\d+(?:\.\d+)*(?:\s*(?:,|and)\s*\d+(?:\.\d+)*)*)")
_NUMBER = re.compile(r"\d+(?:\.\d+)*")
_BRACE = re.compile(r"\{([^{}]{1,200})\}")
_NUM = r"(?P<num>(?:SPM|TS|ES|\d{1,2})\.\d+(?:\.\d+)*)(?P<panel>[a-z](?![a-z]))?"
_CAPTION = re.compile(rf"\b(?P<kind>Cross-Chapter\s+Box|Boxes|Box|Figures?|Fig\.|Tables?|FAQs?)\s+{_NUM}")
_LIST_NEXT = re.compile(rf"\s*(?:,\s*(?:and\s+)?|\s+and\s+|\s+or\s+){_NUM}")   # "Figures 2.26 and 3.26", "Tables 1.1, 1.2"

ASSESSMENT_AUTHORS = {"IPCC"}
_KIND_NAME = {"cross-chapter box": "Cross-Chapter Box", "box": "Box", "boxes": "Box", "figure": "Figure",
              "figures": "Figure", "fig.": "Figure", "table": "Table", "tables": "Table", "faq": "FAQ", "faqs": "FAQ"}


@dataclass(frozen=True)
class Mention:
    kind: str                 # paper | assessment | section | figure | table | box | faq
    label: str                # how it reads in the text, normalised ("Freeman et al., 2017", "Figure 2.11")
    parsed: dict = field(default_factory=dict, hash=False, compare=False)

    @property
    def key(self) -> tuple[str, str]:
        return (self.kind, self.label)


def caption_label(kind: str, num: str) -> tuple[str, str]:
    """('Cross-Chapter  Box', '2.1') -> ('box', 'Cross-Chapter Box 2.1')."""
    name = _KIND_NAME[" ".join(kind.lower().split())]
    short = {"Cross-Chapter Box": "box", "Box": "box", "Figure": "figure", "Table": "table", "FAQ": "faq"}[name]
    return short, f"{name} {num}"


def author_count(base: str) -> tuple[int, str]:
    """'Kent and Kennedy' -> (2, 'Kennedy'); 'Freeman et al.' -> (3, ''); 'Hawkins' -> (1, '')."""
    if re.search(r"\bet\s+al", base):
        return 3, ""
    parts = re.split(r"\s+(?:and|&)\s+", base, maxsplit=1)
    return (2, parts[1].strip()) if len(parts) == 2 else (1, "")


def _papers(text: str) -> list[Mention]:
    found: list[Mention] = []

    def add(m: re.Match, base: str) -> None:
        author = m.group("author")
        kind = "assessment" if author in ASSESSMENT_AUTHORS else "paper"
        n_authors, second = author_count(base)
        for year in _YEAR.findall(m.group("years")):
            found.append(Mention(kind, f"{base}, {year}",
                                 {"author": author, "year": year, "n_authors": n_authors, "second": second}))

    for group in _PAREN.findall(text):
        for part in group.split(";"):
            m = _CITE.search(part)
            if m:
                add(m, part[m.start():m.start("years")].rstrip(", ").strip())
    for m in _NARRATIVE.finditer(text):
        add(m, text[m.start():m.start("years")].rstrip("( ").strip())
    return found


def _sections(text: str) -> list[Mention]:
    found = [Mention("section", f"Section {n}", {"number": n})
             for m in _SECTION.finditer(text) for n in _NUMBER.findall(m.group(1))]
    for brace in _BRACE.findall(text):             # SPM / TS pointers: {2.3.1.1, Figure 2.1}
        for item in re.split(r"[,;]\s*", brace):
            item = item.strip()
            if re.fullmatch(r"\d+(?:\.\d+)*", item):
                found.append(Mention("section", f"Section {item}", {"number": item}))
    return found


def _captions(text: str) -> list[Mention]:
    found = []
    for m in _CAPTION.finditer(text):
        nums, pos = [m], m.end()
        while more := _LIST_NEXT.match(text, pos):         # "Figures 2.26 and 3.26": every number is a mention
            nums.append(more)
            pos = more.end()
        for n in nums:
            kind, label = caption_label(m.group("kind"), n.group("num"))
            found.append(Mention(kind, label, {"number": n.group("num"), "panel": n.group("panel") or ""}))
    return found


def extract_mentions(text: str) -> list[Mention]:
    """All mentions in one sentence, each once: papers first, then sections, then figures / tables / boxes."""
    seen: set[tuple[str, str]] = set()
    out = []
    for m in _papers(text) + _sections(text) + _captions(text):
        if m.key not in seen:
            seen.add(m.key)
            out.append(m)
    return out
