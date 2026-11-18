import time

import pytest
from fastapi.testclient import TestClient

from climate_claims.schemas import Analysis
from climate_claims.web import app as web

ANALYSIS = {
    "claim": "Human influence has warmed the atmosphere, ocean and land.",
    "claim_type": "causal_attribution", "type_reason": "asserts a cause",
    "literal_meaning": "m", "implied_argument": "i",
    "ambiguities": [{"term_or_relation": "Human influence", "possible_meanings": ["GHG", "aerosols"]}],
    "hidden_assumptions": ["records are reliable"],
    "type_mismatch": {"detected": False, "premise_type": "x", "conclusion_type": "y", "explanation": "z"},
}


class FakeAnalysis:
    def to_dict(self):
        return ANALYSIS


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(web, "analyze", lambda claim: FakeAnalysis())
    monkeypatch.setattr(web, "get_retriever", lambda: object())

    def fake_run(analysis, retriever, on_entry=None):
        entry = {"about": "claim", "query": analysis.claim, "findings": []}
        on_entry(entry, 1, 1)
        return {"claim": analysis.claim, "evidence": [entry]}

    monkeypatch.setattr(web, "run_evidence", fake_run)
    return TestClient(web.app)


def test_index_page_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Debatable" in r.text
    assert client.get("/static/app.js").status_code == 200


def test_analyze(client):
    r = client.post("/api/analyze", json={"claim": "Human influence has warmed the atmosphere."})
    assert r.status_code == 200 and r.json()["claim_type"] == "causal_attribution"


def test_analyze_rejects_empty_claim(client):
    assert client.post("/api/analyze", json={"claim": ""}).status_code == 422


def test_analyze_reports_missing_model_config(client, monkeypatch):
    def boom(_):
        raise SystemExit("Set OPENWEBUI_API_KEY and OPENWEBUI_MODEL (see .env.example).")
    monkeypatch.setattr(web, "analyze", boom)
    r = client.post("/api/analyze", json={"claim": "anything here"})
    assert r.status_code == 503 and "OPENWEBUI_API_KEY" in r.json()["detail"]


def test_evidence_job_runs_and_can_be_polled(client):
    job = client.post("/api/evidence", json={"analysis": ANALYSIS}).json()["job"]
    for _ in range(50):
        state = client.get(f"/api/evidence/{job}").json()
        if state["status"] != "running":
            break
        time.sleep(0.05)
    assert state["status"] == "done" and state["result"]["evidence"][0]["query"] == ANALYSIS["claim"]


def test_evidence_rejects_bad_analysis(client):
    assert client.post("/api/evidence", json={"analysis": {"claim": "x"}}).status_code == 422
    assert client.get("/api/evidence/nope").status_code == 404


def test_job_error_is_reported_not_left_running(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("index is empty")
    monkeypatch.setattr(web, "run_evidence", boom)
    job = client.post("/api/evidence", json={"analysis": ANALYSIS}).json()["job"]
    for _ in range(50):
        state = client.get(f"/api/evidence/{job}").json()
        if state["status"] != "running":
            break
        time.sleep(0.05)
    assert state["status"] == "error" and "index is empty" in state["error"]
