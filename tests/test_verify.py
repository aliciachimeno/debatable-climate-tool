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



    

def test_long_quote_rejected():
    words = " ".join(f"w{i}" for i in range(41))
    w = Window("d.pdf", 0, 0, 0.9, [words], [(1, words)])
    f = {"statement": "s", "passage_id": w.id, "quote": words}
    assert verify([f], [w]) == []


def test_number_in_statement_must_be_in_quote():
    w = Window("d.pdf", 0, 0, 0.9, ["Warming reached 1.1 degrees."], [(1, "Warming reached 1.1 degrees.")])
    ok = {"statement": "It reached 1.1 degrees.", "passage_id": w.id, "quote": "Warming reached 1.1 degrees."}
    bad = {"statement": "It reached 1.5 degrees.", "passage_id": w.id, "quote": "Warming reached 1.1 degrees."}
    assert len(verify([ok], [w])) == 1
    assert verify([bad], [w]) == []


def test_strength_is_extracted():
    from climate_claims.evidence.strength import strength
    assert strength("It is unequivocal that human influence has warmed the atmosphere.")["stated_as_fact"]
    s = strength("It is extremely likely that humans caused it (very high confidence).")
    assert (s["likelihood"], s["confidence"]) == ("extremely likely", "very high")
    assert strength("Warming was observed.") == {"likelihood": None, "confidence": None, "stated_as_fact": False}
