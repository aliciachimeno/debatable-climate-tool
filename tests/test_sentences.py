from climate_claims.indexing.sentences import clean, split_pages


def test_clean_joins_hyphenated_line_breaks():
    assert clean("global warm-\ning is   real") == "global warming is real"


def test_split_pages_keeps_page_numbers():
    out = split_pages([(1, "Temperature rose. Seas rose too."), (2, "Ice melted.")])
    assert [p for p, _ in out] == [1, 1, 2]
    assert out[0][1] == "Temperature rose."