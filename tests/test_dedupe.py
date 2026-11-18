from climate_claims.evidence.dedupe import dedupe_findings, source_rank


def finding(doc, pages, quote="It is unequivocal that human influence has warmed the atmosphere."):
    return {"statement": "s", "quote": quote, "document": doc, "pages": pages, "passage_id": f"{doc}:0-1"}


def test_source_rank_prefers_chapters_over_summaries():
    ranks = [source_rank(d) for d in ("IPCC_AR6_WGI_Chapter03.pdf", "IPCC_AR6_WGI_TS.pdf",
                                      "IPCC_AR6_WGI_SPM.pdf", "IPCC_AR6_SYR_SPM.pdf")]
    assert ranks == sorted(ranks) and len(set(ranks)) == 4


def test_duplicates_collapse_to_the_chapter():
    entries = [
        {"about": "claim", "query": "q1", "findings": [finding("IPCC_AR6_SYR_SPM.pdf", [11])]},
        {"about": "assumption", "query": "q2", "findings": [
            finding("IPCC_AR6_WGI_Chapter03.pdf", [3]), finding("IPCC_AR6_WGI_Chapter01.pdf", [26])]},
    ]
    out = dedupe_findings(entries)
    kept = [f for e in out for f in e["findings"]]
    assert len(kept) == 1
    assert kept[0]["document"].startswith("IPCC_AR6_WGI_Chapter0")
    assert {a["document"] for a in kept[0]["also_in"]} >= {"IPCC_AR6_SYR_SPM.pdf"}
    assert out[0]["findings"] == []            # the summary copy was removed from the first question


def test_distinct_quotes_are_kept():
    entries = [{"about": "claim", "query": "q", "findings": [
        finding("a.pdf", [1], "One thing."), finding("a.pdf", [2], "Another thing.")]}]
    assert len(dedupe_findings(entries)[0]["findings"]) == 2
