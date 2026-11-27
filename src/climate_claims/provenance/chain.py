"""The evidence chain of a finding: the papers, sections and figures its quote points to.

Reads provenance.json (made by `claims provenance`); with no file, findings simply carry no chain.
The browser has a port of `for_span` (web/static/js/provenance.js); tests keep the two equal."""
import json
from pathlib import Path

from ..config import settings
from ..sources import source_url

STATUS_NOTE = {"not_indexed": "in a document that is not indexed", "not_found": "not found in the document"}
MAX_CANDIDATES = 4


_CACHE: dict = {}


def _doi_url(doi: str) -> str:
    return f"https://doi.org/{doi}"


class ProvenanceIndex:
    def __init__(self, data: dict):
        self.data = data
        self._refs = {doc: {r["id"]: r for r in d["references"]} for doc, d in data["docs"].items()}

    @classmethod
    def load(cls, path: Path | None = None) -> "ProvenanceIndex | None":
        path = Path(path or settings.provenance_file)
        if not path.exists():
            return None
        return cls(json.loads(path.read_text(encoding="utf-8")))

    @classmethod
    def cached(cls) -> "ProvenanceIndex | None":
        """The index at settings.provenance_file, loaded once and reloaded if the file changes."""
        path = Path(settings.provenance_file)
        stamp = path.stat().st_mtime_ns if path.exists() else None
        if _CACHE.get("key") != (path, stamp):
            _CACHE.update(key=(path, stamp), value=cls.load(path))
        return _CACHE["value"]

    def _reference(self, doc: str, ref_id: str) -> dict:
        r = self._refs[doc][ref_id]
        out = {"id": ref_id, "text": r["raw"], "title": r["title"], "page": r["page"], "document": doc,
               "url": source_url(doc, r["page"])}
        if r.get("doi"):
            out["doi"], out["doi_url"] = r["doi"], _doi_url(r["doi"])
        return out

    def _paper(self, doc: str, e: dict) -> dict:
        item = {"label": e["l"], "type": "assessment" if e["k"] == "assessment" else "study", "status": e["s"]}
        if "c" in e:
            item["confidence"] = e["c"]
        refs = e.get("r")
        if e["s"] == "resolved":
            item["reference"] = self._reference(doc, refs)
        elif e["s"] == "ambiguous":
            item["candidates"] = [self._reference(doc, r) for r in refs[:MAX_CANDIDATES]]
        return item

    def _section(self, e: dict) -> dict:
        item = {"label": e["l"], "status": e["s"]}
        if e["s"] == "resolved":
            s = self.data["docs"][e["d"]]["sections"][e["n"]]
            item.update(document=e["d"], page=s["page"], url=source_url(e["d"], s["page"]), range=[s["lo"], s["hi"]])
            if s["title"]:
                item["title"] = s["title"]
        return item

    def _figure(self, e: dict) -> dict:
        item = {"label": e["l"], "kind": e["k"], "status": e["s"]}
        if e["s"] == "resolved":
            c = self.data["docs"][e["d"]]["captions"][e["n"]]
            item.update(document=e["d"], page=c["page"], title=c["title"], url=source_url(e["d"], c["page"]))
            for key in ("data_url", "code_url"):
                if c.get(key):
                    item[key] = c[key]
            if c.get("url"):
                item["figure_url"] = c["url"]
            if index := self.data["docs"][e["d"]].get("figure_index"):
                item["index_url"] = index
        return item

    def for_span(self, doc: str, lo: int, hi: int) -> dict | None:
        """Everything the sentences lo..hi of `doc` point to, each item once, in reading order."""
        edges = self.data["edges"].get(doc, {})
        seen, out = set(), {"papers": [], "sections": [], "figures": []}
        for idx in range(lo, hi + 1):
            for e in edges.get(str(idx), ()):
                if (e["k"], e["l"]) in seen:
                    continue
                seen.add((e["k"], e["l"]))
                if e["k"] in ("paper", "assessment"):
                    out["papers"].append(self._paper(doc, e))
                elif e["k"] == "section":
                    out["sections"].append(self._section(e))
                else:
                    out["figures"].append(self._figure(e))
        return out if any(out.values()) else None
