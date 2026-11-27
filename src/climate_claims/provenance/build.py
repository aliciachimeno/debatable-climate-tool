"""Build provenance.json from the indexed sentences: references, sections, captions, and for every
sentence the links its mentions resolve to. Runs once after `claims index`, offline, no LLM."""
import json
from collections import Counter
from pathlib import Path

from ..config import settings
from .mentions import extract_mentions
from .references import ReferenceTable, parse_references
from .resolve import DocData, Resolver, doc_key
from .structure import find_captions, find_sections

VERSION = 1
FIGURE_INDEX = {"WGI": "https://www.ipcc.ch/report/ar6/wg1/figures"}   # the IPCC page that lists every WGI figure


def build_from_rows(docs: dict[str, list[tuple[int, int, str]]], figure_links: dict | None = None) -> dict:
    """docs: {name: [(idx, page, text), ...]} in reading order. Pure: no files, no network."""
    figure_links = figure_links or {}
    parsed: dict[str, dict] = {}
    data: dict[str, DocData] = {}
    for doc, rows in docs.items():
        refs, start = parse_references(rows)
        captions = find_captions(rows, start)
        for label, links in figure_links.get(doc, {}).items():       # optional per-figure links (url, data_url, code_url)
            if label in captions:
                captions[label].update({k: v for k, v in links.items() if v})
        sections = find_sections(rows)
        data[doc] = DocData(ReferenceTable(refs) if refs else None, sections, captions)
        report, part = doc_key(doc)
        parsed[doc] = {"report": report, "part": part, "ref_start": start,
                       "references": [r.to_dict() for r in refs], "sections": sections, "captions": captions}
        if report in FIGURE_INDEX:
            parsed[doc]["figure_index"] = FIGURE_INDEX[report]

    resolver = Resolver(data)
    edges: dict[str, dict[str, list]] = {}
    stats = {d: Counter() for d in docs}
    for doc, rows in docs.items():
        stop = parsed[doc]["ref_start"]
        for idx, _, text in rows:
            if stop is not None and idx >= stop:
                break
            found = [resolver.resolve(doc, m) for m in extract_mentions(text)]
            if found:
                edges.setdefault(doc, {})[str(idx)] = found
                for e in found:
                    stats[doc][f'{e["k"]}:{e["s"]}'] += 1
    return {"version": VERSION, "docs": parsed, "edges": edges,
            "stats": {d: dict(sorted(c.items())) for d, c in stats.items()}}


def build_provenance(store, out: Path | None = None) -> dict:
    docs = {}
    for doc, *_ in store.stats():
        docs[doc] = store.doc_rows(doc)
    links_file = Path(settings.figure_links_file)
    links = json.loads(links_file.read_text(encoding="utf-8")) if links_file.exists() else None
    result = build_from_rows(docs, links)
    out = Path(out or settings.provenance_file)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return result


def coverage_report(result: dict) -> str:
    lines = []
    for doc, d in result["docs"].items():
        lines.append(f"{doc}: {len(d['references'])} references ({sum('doi' in r for r in d['references'])} with DOI), "
                     f"{len(d['sections'])} sections, {len(d['captions'])} captions")
        by_kind: dict[str, Counter] = {}
        for key, n in result["stats"].get(doc, {}).items():
            kind, status = key.split(":")
            by_kind.setdefault(kind, Counter())[status] = n
        for kind, c in sorted(by_kind.items()):
            total = sum(c.values())
            lines.append(f"   {kind:<10} {total:>5} mentions: " +
                         ", ".join(f"{s} {n} ({100 * n // total}%)" for s, n in c.most_common()))
    return "\n".join(lines)
