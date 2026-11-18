import re
import warnings

# pysbd has old-style regex strings that Python 3.12+ flags when first compiling it
warnings.filterwarnings("ignore", category=SyntaxWarning)
import pysbd  # noqa: E402

_segmenter = pysbd.Segmenter(language="en", clean=False)


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