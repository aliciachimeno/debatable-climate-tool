import json
from functools import lru_cache

from .config import settings
from .schemas import Finding


@lru_cache(maxsize=1)
def _load() -> dict:
    path = settings.sources_file
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def page_url(url: str, page: int) -> str:
    return f"{url}#page={page}" if url else ""


def add_link(finding: Finding) -> Finding:
    info = _load().get(finding.document, {})
    finding.label = info.get("label", finding.document)
    finding.url = page_url(info.get("url", ""), finding.pages[0])
    return finding