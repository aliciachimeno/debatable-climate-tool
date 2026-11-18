import hashlib
from pathlib import Path
from typing import Iterator

from pypdf import PdfReader
import fitz  # pip install pymupdf


def read_pdf(path: Path) -> Iterator[tuple[int, str]]:
    for page_no, page in enumerate(PdfReader(path).pages, 1):
        yield page_no, page.extract_text() or ""


# add new formats here (e.g. ".txt": read_txt) and the indexer picks them up
READERS = {".pdf": read_pdf}


def iter_documents(raw_dir: Path) -> list[Path]:
    raw_dir = Path(raw_dir)
    if not raw_dir.exists():
        return []
    return sorted(p for p in raw_dir.iterdir() if p.suffix.lower() in READERS)


def read_pages(path):
    with fitz.open(path) as doc:
        for i, page in enumerate(doc, start=1):
            yield i, page.get_text("text")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()