"""Turn a mention into a link: which reference, section or caption it points to, and how sure we are.

Status values (kept in the output so failures are visible, never dropped):
  resolved           found, one candidate
  ambiguous          several candidates (listed)
  not_found          the target document is indexed but the target is not in it
  not_indexed        the target lives in a document we do not have
  no_reference_list  a citation in a document whose reference list we did not parse
"""
import re
from dataclasses import dataclass

from .mentions import Mention
from .references import ReferenceTable
from .structure import MAX_TITLE  # noqa: F401  (re-exported for callers that build captions)


def doc_key(doc: str) -> tuple[str, int | str | None]:
    """'IPCC_AR6_WGI_Chapter02.pdf' -> ('WGI', 2); 'IPCC_AR6_WGI_SPM.pdf' -> ('WGI', 'SPM')."""
    stem = doc.removesuffix(".pdf")
    m = re.search(r"AR6_(WGI{0,2}|SYR)(?=_|$)", stem)
    report = m.group(1) if m else stem
    if ch := re.search(r"Chapter0*(\d+)", stem):
        return report, int(ch.group(1))
    if re.search(r"_SPM(?=_|$)", stem):
        return report, "SPM"
    if re.search(r"_TS(?=_|$)", stem):
        return report, "TS"
    return report, None


@dataclass
class DocData:
    table: ReferenceTable | None
    sections: dict[str, dict]
    captions: dict[str, dict]


class Resolver:
    def __init__(self, docs: dict[str, DocData]):
        self.docs = docs
        self.by_key = {doc_key(d): d for d in docs}

    def _target(self, doc: str, part: int | str) -> str | None:
        return self.by_key.get((doc_key(doc)[0], part))

    def resolve(self, doc: str, m: Mention) -> dict:
        if m.kind in ("paper", "assessment"):
            return self._paper(doc, m)
        if m.kind == "section":
            return self._section(doc, m)
        return self._caption(doc, m)

    def _paper(self, doc: str, m: Mention) -> dict:
        edge = {"k": m.kind, "l": m.label}
        table = self.docs[doc].table
        if table is None:
            return {**edge, "s": "no_reference_list"}
        p = m.parsed
        status, conf, found = table.match(p["author"], p["year"], p.get("n_authors"), p.get("second", ""))
        edge.update(s=status, c=conf)
        if status == "resolved":
            edge["r"] = found[0].id
        elif status == "ambiguous":
            edge["r"] = [r.id for r in found[:4]]
        return edge

    def _section(self, doc: str, m: Mention) -> dict:
        edge = {"k": "section", "l": m.label}
        number = m.parsed["number"]
        report, part = doc_key(doc)
        target = None if report == "SYR" else self._target(doc, int(number.split(".")[0]))
        if target is None:
            return {**edge, "s": "not_indexed"}
        found = number in self.docs[target].sections
        return {**edge, "s": "resolved" if found else "not_found", "d": target, "n": number}

    def _caption(self, doc: str, m: Mention) -> dict:
        edge = {"k": m.kind, "l": m.label}
        first = m.parsed["number"].split(".")[0]
        target = self._target(doc, int(first) if first.isdigit() else first)
        if target is None:
            return {**edge, "s": "not_indexed"}
        captions = self.docs[target].captions
        for label in (m.label, f"Cross-Chapter {m.label}", m.label.replace("Cross-Chapter ", "")):
            if label in captions:
                return {**edge, "s": "resolved", "d": target, "n": label}
        return {**edge, "s": "not_found", "d": target}
