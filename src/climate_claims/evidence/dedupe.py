"""Collapse the same quote found in several documents or for several questions.

One finding often travels up the report chain (chapter -> TS -> SPM -> synthesis report).
Those are copies of one finding, not independent evidence, so we keep the occurrence in the
document that does the assessment and list the others under `also_in`.
"""
import re

from .verify import norm

# Lower rank = more primary. Chapters assess the literature; summaries repeat it.
_RANKS = [(re.compile(r"chapter|_ch\d", re.I), 0),
          (re.compile(r"(^|[_\W])TS([_\W]|$)|technical.?summary", re.I), 1),
          (re.compile(r"SYR|synthesis", re.I), 3),          # before SPM: SYR_SPM is a synthesis
          (re.compile(r"SPM|summary.?for.?policy", re.I), 2)]


def source_rank(doc: str) -> int:
    for pattern, rank in _RANKS:
        if pattern.search(doc):
            return rank
    return 1


def dedupe_findings(entries: list[dict]) -> list[dict]:
    """entries: result['evidence']. Returns the same structure, one finding per distinct quote."""
    groups: dict[str, list[tuple[int, int]]] = {}
    for ei, e in enumerate(entries):
        for fi, f in enumerate(e["findings"]):
            groups.setdefault(norm(f["quote"]), []).append((ei, fi))

    drop: set[tuple[int, int]] = set()
    for members in groups.values():
        if len(members) == 1:
            continue
        keep = min(members, key=lambda m: (source_rank(entries[m[0]]["findings"][m[1]]["document"]), m))
        primary = entries[keep[0]]["findings"][keep[1]]
        seen = {(primary["document"], tuple(primary["pages"]))}
        for m in members:
            if m == keep:
                continue
            f = entries[m[0]]["findings"][m[1]]
            key = (f["document"], tuple(f["pages"]))
            if key not in seen:
                seen.add(key)
                primary.setdefault("also_in", []).append({"document": f["document"], "pages": f["pages"]})
            drop.add(m)

    return [{**e, "findings": [f for fi, f in enumerate(e["findings"]) if (ei, fi) not in drop]}
            for ei, e in enumerate(entries)]
