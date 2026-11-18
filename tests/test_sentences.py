from climate_claims.indexing.sentences import clean, split_pages


def test_clean_joins_hyphenated_line_breaks():
    assert clean("global warm-\ning is   real") == "global warming is real"


def test_split_pages_keeps_page_numbers():
    out = split_pages([(1, "Temperature rose. Seas rose too."), (2, "Ice melted.")])
    assert [p for p, _ in out] == [1, 1, 2]
    assert out[0][1] == "Temperature rose."

def test_sentence_kind_filters_non_evidence():
    from climate_claims.indexing.sentences import sentence_kind
    assert sentence_kind("Figure 3.1 | Global temperature anomaly over land and ocean.") == "caption"
    assert sentence_kind("(b) Global temperature anomaly over land and ocean.") == "caption"
    assert sentence_kind("Left: Main realms of the climate system.") == "caption"
    assert sentence_kind("See atmosphere (Section 3.3), cryosphere (Section 3.4) and ocean (Section 3.5).") == "pointer"
    assert sentence_kind("Hegerl, G.C., et al., 2011: Detection of human influence. J. Climate, 24, 1-15.") == "reference"
    # findings with many citations or a couple of section pointers are still evidence
    assert sentence_kind("Warming is human-caused (Hegerl et al., 2011; Stott et al., 2010; Jones et al., 2013; Li et al., 2014; Wu et al., 2015).") == "body"
    assert sentence_kind("This provides high confidence in detection and attribution (Section 3.5.1; Section 3.8).") == "body"
    assert sentence_kind("It is unequivocal that human influence has warmed the atmosphere.") == "body"
