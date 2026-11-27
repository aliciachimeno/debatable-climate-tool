import sqlite3
from pathlib import Path

import pytest

from climate_claims import sources
from climate_claims.evidence import pipeline
from climate_claims.evidence.verify import locate_span, verify
from climate_claims.provenance import ProvenanceIndex, build_from_rows
from climate_claims.provenance.mentions import extract_mentions
from climate_claims.provenance.references import (ReferenceTable, author_key, merge_fragments, parse_references,
                                                  strip_page_header)
from climate_claims.provenance.resolve import doc_key
from climate_claims.provenance.structure import find_captions, find_sections
from climate_claims.schemas import EvidenceNeed, Window

DOC = "IPCC_AR6_WGI_Chapter02.pdf"
SOURCES = {DOC: {"url": "https://example.org/ch2.pdf"}}


def labels(text, kind=None):
    return [m.label for m in extract_mentions(text) if kind is None or m.kind == kind]


# ---- mentions ----
def test_paper_citations_several_authors_and_years():
    text = "It rose (Freeman et al., 2017, 2019; Kent and Kennedy, 2021; Hawkins, 2012a)."
    assert labels(text, "paper") == ["Freeman et al., 2017", "Freeman et al., 2019",
                                     "Kent and Kennedy, 2021", "Hawkins, 2012a"]


def test_narrative_citation_and_assessment():
    found = extract_mentions("Hawkins and Sutton (2012) found it, as did AR5 (IPCC, 2013).")
    by_label = {m.label: m for m in found}
    assert {(m.kind, m.label) for m in found} == {("paper", "Hawkins and Sutton, 2012"), ("assessment", "IPCC, 2013")}
    assert by_label["Hawkins and Sutton, 2012"].parsed["n_authors"] == 2
    assert by_label["Hawkins and Sutton, 2012"].parsed["second"] == "Sutton"


def test_particles_and_year_ranges_are_not_citations():
    assert labels("Warmed since 1850–1900 (see von Schuckmann et al., 2019).", "paper") == ["von Schuckmann et al., 2019"]
    assert labels("The period (1850–1900) was cool.") == []


def test_section_figure_box_mentions():
    text = "{2.3.1.1, Cross-Chapter Box 2.1} See Section 1.4.1 and Figure 2.11a, Table 2.1 and FAQ 2.2."
    got = {(m.kind, m.label) for m in extract_mentions(text)}
    assert got == {("section", "Section 2.3.1.1"), ("box", "Cross-Chapter Box 2.1"), ("section", "Section 1.4.1"),
                   ("figure", "Figure 2.11"), ("table", "Table 2.1"), ("faq", "FAQ 2.2")}


def test_plural_lists_give_one_mention_per_number():
    text = "(Section 3.5.1.3 and Figures 2.26 and 3.26), then Tables 1.1, 1.2 and 1.3 but not Table 2.1, 2020."
    assert labels(text, "figure") == ["Figure 2.26", "Figure 3.26"]
    assert labels(text, "table") == ["Table 1.1", "Table 1.2", "Table 1.3", "Table 2.1"]


def test_each_mention_once():
    assert labels("Figure 2.1 and again Figure 2.1; (Kent et al., 2020; Kent et al., 2020)") == ["Kent et al., 2020", "Figure 2.1"]


# ---- reference list ----
HEADER = "382 Chapter 2\x08 Changing State of the Climate System 2 "


def ref_rows():
    texts = [
        "Body text.",
        HEADER + "References Freeman, E. et al., 2017: Better sea surface data.",
        "Journal of Climate, 30(1), 1–10, doi:10.1000/ abc123.",
        "Freeman, E. and T. Smith, 2017: A pair paper.",
        "Journal, 2, 3–4, doi:10.1000/pair.",
        "Kent, E.C. and J.J. Kennedy, 2021: Another study.",
        "Nature, 5, 1–2, doi:10.1000/x. Ahn, M.",
        "-S. et al., 2018: Fragment entry.",
        "Journal, 9, 9–10.",
    ]
    return [(i, 1 + i // 4, t) for i, t in enumerate(texts)]


def test_strip_page_header():
    assert strip_page_header(HEADER + "References Kent, E.C.").startswith("References Kent")
    assert strip_page_header("Plain sentence.") == "Plain sentence."


def test_merge_fragments_rejoins_author_lists():
    merged = merge_fragments([(0, 1, "Ahn, M."), (1, 1, "-S. et al., 2018: Title."), (2, 1, "Next.")])
    assert [t for _, _, t in merged] == ["Ahn, M.-S. et al., 2018: Title.", "Next."]


def test_parse_references():
    refs, start = parse_references(ref_rows())
    assert start == 1
    assert [(r.author, r.year) for r in refs] == [("Freeman", "2017"), ("Freeman", "2017"), ("Kent", "2021"), ("Ahn", "2018")]
    assert refs[0].doi == "10.1000/abc123"                      # space inside the DOI rejoined
    assert refs[0].title == "Better sea surface data."
    assert refs[1].n_authors == 2 and refs[0].n_authors == 3 and refs[2].second == "Kennedy"
    assert refs[2].doi == "10.1000/x" and refs[3].doi is None   # cut at the DOI; the fragment became its own entry


def test_match_statuses():
    refs, _ = parse_references(ref_rows())
    table = ReferenceTable(refs)
    assert table.match("Kent", "2021")[:2] == ("resolved", 1.0)
    assert table.match("Freeman", "2017")[0] == "ambiguous"
    status, conf, found = table.match("Freeman", "2017", n_authors=3)       # "Freeman et al." = 3 or more
    assert (status, conf, found[0].n_authors) == ("resolved", 0.9, 3)
    assert table.match("Freeman", "2017", n_authors=2)[0] == "resolved"
    assert table.match("Kent", "2021b")[:2] == ("resolved", 0.8)            # suffix on one side only
    assert table.match("Nobody", "2001")[0] == "not_found"
    assert author_key("von Schuckmann") == author_key("Von-Schuckmann") == "vonschuckmann"


# ---- structure ----
def body_rows():
    texts = ["2.1 Introduction This chapter assesses it.",
             "Text. 2.1.1 Temperature 2.1.2 Rain Rain text.",
             "Figure 2.1 | Global temperature. More caption.",
             "2.2 Drivers Forcing text.",
             "Cross-Chapter Box 2.1 | Reference periods Contributing Authors: A. B.",
             "A stray 2.7 Ma value appears here.",
             "2.5 °C of warming."]
    return [(i, 1, t) for i, t in enumerate(texts)]


def test_sections_ranges_and_stray_numbers():
    sec = find_sections(body_rows())
    assert set(sec) == {"2.1", "2.1.1", "2.1.2", "2.2"}
    assert (sec["2.1"]["lo"], sec["2.1"]["hi"]) == (0, 2)            # runs until 2.2
    assert sec["2.1.1"]["title"] == "Temperature" and sec["2.1.2"]["hi"] == 2
    assert sec["2.2"]["hi"] == 6


def test_captions():
    caps = find_captions(body_rows())
    assert caps["Figure 2.1"]["title"] == "Global temperature. More caption."
    assert caps["Cross-Chapter Box 2.1"]["title"] == "Reference periods"


def test_doc_key():
    assert doc_key("IPCC_AR6_WGI_Chapter02.pdf") == ("WGI", 2)
    assert doc_key("IPCC_AR6_WGI_SPM.pdf") == ("WGI", "SPM")
    assert doc_key("IPCC_AR6_SYR_SPM.pdf") == ("SYR", "SPM")


# ---- the whole chain ----
def chapter_rows():
    cites = ("Warming is documented (Freeman et al., 2017; Kent and Kennedy, 2021) and shown in Figure 2.1; "
             "see Section 2.1.1, Section 4.2 and Box 9.9.")
    rows = [(0, 1, "2.1 Introduction This chapter assesses it."), (1, 1, cites),
            (2, 2, "2.1.1 Temperature Surface temperature rose {2.1.1}."),
            (3, 2, "Figure 2.1 | Global temperature.")]
    return rows + [(10 + i, 3, t) for i, (_, _, t) in enumerate(ref_rows())]


def test_build_and_for_span(monkeypatch):
    monkeypatch.setattr(sources, "_load", lambda: SOURCES)
    data = build_from_rows({DOC: chapter_rows()})
    chain = ProvenanceIndex(data).for_span(DOC, 1, 1)
    papers = {p["label"]: p for p in chain["papers"]}
    assert papers["Freeman et al., 2017"]["reference"]["doi_url"] == "https://doi.org/10.1000/abc123"
    assert papers["Freeman et al., 2017"]["confidence"] == 0.9
    assert papers["Kent and Kennedy, 2021"]["status"] == "resolved"
    sec = {s["label"]: s for s in chain["sections"]}
    assert sec["Section 2.1.1"]["status"] == "resolved" and sec["Section 2.1.1"]["url"].endswith("#page=2")
    assert sec["Section 4.2"]["status"] == "not_indexed"                 # chapter 4 is not in the index
    figs = {f["label"]: f for f in chain["figures"]}
    assert figs["Figure 2.1"]["title"] == "Global temperature."
    assert figs["Box 9.9"]["status"] == "not_indexed"
    assert ProvenanceIndex(data).for_span(DOC, 0, 0) is None             # nothing cited: no chain
    assert ProvenanceIndex(data).for_span(DOC, 1, 3)["sections"][0]["label"] == "Section 2.1.1"   # spans merge, in order


def test_reference_list_sentences_are_not_mined():
    data = build_from_rows({DOC: chapter_rows()})
    assert max(int(i) for i in data["edges"][DOC]) < 11                 # nothing from the reference list itself


# ---- finding span ----
def test_locate_span_and_verify_sets_it():
    w = Window("d.pdf", 5, 7, 0.9, ["b"], [(1, "Alpha beta."), (1, "Gamma delta."), (2, "Epsilon zeta.")])
    assert locate_span("Gamma delta. Epsilon zeta.", w) == [6, 7]
    assert locate_span("made up", w) is None
    [f] = verify([{"statement": "s", "passage_id": w.id, "quote": "Gamma delta."}], [w])
    assert f.span == [6, 6] and f.provenance is None


# ---- the real index (skipped when the repo has no index) ----
INDEX = Path("data/index/sentences.db")


@pytest.mark.skipif(not INDEX.exists(), reason="no index in this checkout")
def test_real_chapter_coverage():
    db = sqlite3.connect(f"file:{INDEX}?mode=ro", uri=True)
    docs = {d: db.execute("SELECT idx, page, text FROM sentences WHERE doc=? ORDER BY idx", (d,)).fetchall()
            for (d,) in db.execute("SELECT DISTINCT doc FROM sentences WHERE doc LIKE '%Chapter02%'")}
    if not docs:
        pytest.skip("Chapter 2 is not indexed")
    data = build_from_rows(docs)
    d = data["docs"][DOC]
    assert len(d["references"]) > 1200 and sum("doi" in r for r in d["references"]) > 0.95 * len(d["references"])
    assert "2.3.1.1" in d["sections"] and "Figure 2.11" in d["captions"]
    s = data["stats"][DOC]
    papers = sum(v for k, v in s.items() if k.startswith("paper:"))
    assert s["paper:resolved"] / papers > 0.85                          # in-text citations that reach a reference entry


# ---- the pipeline attaches the chain to verified findings ----
def test_pipeline_attaches_provenance(monkeypatch):
    monkeypatch.setattr(sources, "_load", lambda: SOURCES)
    index = ProvenanceIndex(build_from_rows({DOC: chapter_rows()}))
    monkeypatch.setattr(ProvenanceIndex, "cached", classmethod(lambda cls: index))
    rows = chapter_rows()[:4]
    window = Window(DOC, 0, 3, 0.9, [rows[1][2]], [(page, text) for _, page, text in rows])
    quote = rows[1][2]
    monkeypatch.setattr(pipeline, "chat_json", lambda *a, **k: {"findings": [
        {"statement": "s", "passage_id": window.id, "quote": quote, "stance": "supports"}]})
    need = EvidenceNeed("N1", "p", "claim", "", "", "", ["q"])
    [finding] = pipeline._ask("system", need, [window])["findings"]
    assert finding["span"] == [1, 1]
    assert [p["label"] for p in finding["provenance"]["papers"]] == ["Freeman et al., 2017", "Kent and Kennedy, 2021"]
    assert finding["provenance"]["figures"][0]["label"] == "Figure 2.1"


def test_pipeline_without_provenance_file_gives_no_chain(monkeypatch):
    monkeypatch.setattr(ProvenanceIndex, "cached", classmethod(lambda cls: None))
    window = Window("d.pdf", 0, 0, 0.9, ["Alpha beta."], [(1, "Alpha beta.")])
    monkeypatch.setattr(pipeline, "chat_json", lambda *a, **k: {"findings": [
        {"statement": "s", "passage_id": window.id, "quote": "Alpha beta."}]})
    [finding] = pipeline._ask("system", EvidenceNeed("N1", "p", "claim", "", "", "", ["q"]), [window])["findings"]
    assert finding["provenance"] is None
