"""Web app: /api/analyze (fast), /api/evidence (slow, runs as a background job you poll).

The interface shows the analysis first; the evidence tab fills in as the job progresses.
"""
import threading
import uuid
from collections import OrderedDict
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..analysis.analyze import analyze
from ..evidence.pipeline import run_evidence
from ..retrieval.retriever import Retriever
from ..schemas import Analysis

STATIC = Path(__file__).parent / "static"
MAX_JOBS = 50


class ClaimIn(BaseModel):
    claim: str = Field(min_length=3, max_length=1000)


class EvidenceIn(BaseModel):
    analysis: dict


# ---- retriever shared by all requests (sqlite + the embedding model are not thread-safe) ----
class _LockedStore:
    def __init__(self, store, lock):
        self._store, self._lock = store, lock

    def doc_hashes(self):
        with self._lock:
            return self._store.doc_hashes()


class SafeRetriever:
    def __init__(self, inner: Retriever):
        self._inner, self._lock = inner, threading.Lock()
        self.store = _LockedStore(inner.store, self._lock)

    def search(self, *args, **kwargs):
        with self._lock:
            return self._inner.search(*args, **kwargs)


_retriever: SafeRetriever | None = None
_retriever_error: str | None = None
_retriever_lock = threading.Lock()


def get_retriever() -> SafeRetriever:
    global _retriever, _retriever_error
    with _retriever_lock:
        if _retriever is None:
            try:
                _retriever, _retriever_error = SafeRetriever(Retriever()), None
            except SystemExit as e:            # Retriever exits when the index is empty
                _retriever_error = str(e) or "The index is empty. Run: claims index"
                raise RuntimeError(_retriever_error) from None
        return _retriever


# ---- background evidence jobs (in memory; fine for a single-process local app) ----
jobs: "OrderedDict[str, dict]" = OrderedDict()
_jobs_lock = threading.Lock()


def _run_job(job_id: str, analysis: Analysis) -> None:
    job = jobs[job_id]

    def on_entry(entry, done, total):
        with _jobs_lock:
            job["entries"].append(entry)
            job["done"], job["total"] = done, total

    try:
        result = run_evidence(analysis, get_retriever(), on_entry=on_entry)
        with _jobs_lock:
            job["result"], job["status"] = result, "done"
    except Exception as e:                      # never leave a job "running" forever
        with _jobs_lock:
            job["error"], job["status"] = str(e), "error"


def create_app() -> FastAPI:
    app = FastAPI(title="Debatable Climate Change tool")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/health")
    def health():
        try:
            get_retriever()
            return {"ok": True, "index_ready": True}
        except RuntimeError as e:
            return {"ok": True, "index_ready": False, "message": str(e)}

    @app.post("/api/analyze")
    def api_analyze(body: ClaimIn):
        try:
            return analyze(body.claim.strip()).to_dict()
        except SystemExit as e:                 # missing API key / model
            raise HTTPException(503, str(e) or "The language model is not configured.")
        except (ValueError, requests.RequestException) as e:
            raise HTTPException(502, f"The language model did not answer correctly: {e}")

    @app.post("/api/evidence", status_code=202)
    def api_evidence(body: EvidenceIn):
        try:
            analysis = Analysis.from_dict(body.analysis)
        except ValueError as e:
            raise HTTPException(422, str(e))
        job_id = uuid.uuid4().hex[:12]
        with _jobs_lock:
            jobs[job_id] = {"status": "running", "done": 0, "total": 0,
                            "entries": [], "result": None, "error": None}
            while len(jobs) > MAX_JOBS:
                jobs.popitem(last=False)
        threading.Thread(target=_run_job, args=(job_id, analysis), daemon=True).start()
        return {"job": job_id}

    @app.get("/api/evidence/{job_id}")
    def api_evidence_status(job_id: str):
        with _jobs_lock:
            job = jobs.get(job_id)
            if job is None:
                raise HTTPException(404, "Unknown job")
            return dict(job)

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
