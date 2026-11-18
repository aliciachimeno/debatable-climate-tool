import re
import warnings

# pysbd has old-style regex strings that Python 3.12+ flags when first compiling it
warnings.filterwarnings("ignore", category=SyntaxWarning)
import pysbd  # noqa: E402

_segmenter = pysbd.Segmenter(language="en", clean=False)


# Sentences that are not evidence: figure/table captions, panel labels, reference lists
# and "see Section x.y" pointers. They stay in the index (context windows read continuously)
# but are never embedded, so they are never retrieved as a hit.
_CAPTION = re.compile(
    r"^(Figure|Fig\.|Table|Box|FAQ|Cross-Chapter Box)\b|^\(?[a-z]\)\s|^(Left|Right|Top|Bottom|Middle):",
    re.I)
_REFLINE = re.compile(r"\b(?:19|20)\d{2}[a-z]?: |\bdoi:|https?://", re.I)    # "Author, 2011: Title."
_SECTION_REF = re.compile(r"\bSections?\s\d+(\.\d+)*")


def sentence_kind(s: str) -> str:
    """'body' for real prose, else 'caption' | 'reference' | 'pointer'."""
    if _CAPTION.search(s):
        return "caption"
    # Only reference-list entries ("Author, 2011: Title"). Findings in the chapters often carry
    # many in-text citations and are real evidence, so those are NOT filtered.
    if _REFLINE.search(s):
        return "reference"
    # Only sentences that are mostly a list of "(Section x.y)" cross-references.
    if len(_SECTION_REF.findall(s)) >= 3:
        return "pointer"
    return "body"


def clean(text: str) -> str:
    text = re.sub(r"-\n(?=[a-z])", "", text)    # undo line-break hyphenation
    return " ".join(text.split())


def split_pages(pages) -> list[tuple[int, str]]:
    """[(page_no, raw_text)] -> [(page_no, sentence)] in reading order."""
    out = []
    for page_no, raw in pages:
        for s in _segmenter.segment(clean(raw)):
            s = s.strip()
            if s:
                out.append((page_no, s))
    return out