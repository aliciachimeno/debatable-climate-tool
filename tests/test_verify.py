from climate_claims.evidence.verify import locate, verify
from climate_claims.schemas import Window


def make_window():
    return Window("doc.pdf", 0, 2, 0.9, ["Gamma delta."],
                  [(1, "Alpha beta."), (1, "Gamma delta."), (2, "Epsilon zeta.")])


def test_exact_quote_single_page():
    assert locate("Gamma delta.", make_window()) == [1]


def test_quote_spanning_two_pages():
    assert locate("Gamma delta. Epsilon zeta.", make_window()) == [1, 2]


def test_case_and_whitespace_insensitive():
    assert locate("gamma   DELTA.", make_window()) == [1]


def test_altered_quote_rejected():
    assert locate("Gamma delta changed.", make_window()) is None
    assert locate("", make_window()) is None



    