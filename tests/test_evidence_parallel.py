import requests

from climate_claims.analysis import plan
from climate_claims.evidence import pipeline
from climate_claims.schemas import Ambiguity, Analysis, TypeMismatch, Window


class FakeStore:
    def doc_hashes(self):
        return {"d.pdf": "abc" * 10}


class FakeRetriever:
    store = FakeStore()

    def search(self, q):
        return [Window("d.pdf", 0, 1, 0.9, ["Alpha."], [(1, "Alpha."), (1, "Beta.")])]


def make_analysis():
    return Analysis(
        claim="c", claim_type="descriptive_factual", type_reason="", literal_meaning="",
        implied_argument="", ambiguities=[Ambiguity("t", ["a", "b"])],
        hidden_assumptions=["h1", "h2"],
        type_mismatch=TypeMismatch(False, "", "", ""))


def test_order_preserved_and_errors_isolated(monkeypatch):
    def fake_chat(system, user, temperature=0.2, retries=2):
        if "h1" in user:
            raise requests.Timeout("slow")
        return {"findings": [{"statement": "s", "quote": "Alpha.", "passage_id": "d.pdf:0-1"}]}

    def no_plan(*args, **kwargs):                      # planning must not need a real model in tests
        raise ValueError("no plan in this test")

    monkeypatch.setattr(pipeline, "chat_json", fake_chat)
    monkeypatch.setattr(plan, "chat_json", no_plan)
    monkeypatch.setattr(pipeline, "load_prompt", lambda name: "sys")

    out = pipeline.run_evidence(make_analysis(), FakeRetriever())
    kinds = [e["about"] for e in out["evidence"]]

    assert kinds == ["claim", "ambiguity", "assumption", "assumption"]
    assert "error" in out["evidence"][2]               # h1 timed out, run continued
    assert out["evidence"][0]["findings"][0]["pages"] == [1]
    assert out["evidence"][3]["findings"]               # h2 ok