from dataclasses import asdict

from ..config import settings
from ..llm import chat_json, load_prompt
from ..retrieval.retriever import Retriever
from ..schemas import Analysis, Window
from .verify import verify


def build_queries(a: Analysis) -> list[tuple[str, str]]:
    queries = [("claim", a.claim)]
    for amb in a.ambiguities:
        queries.append(("ambiguity", f"{amb.term_or_relation}: " + "; ".join(amb.possible_meanings)))
    for h in a.hidden_assumptions:
        queries.append(("assumption", h))
    return queries


def format_windows(windows: list[Window]) -> str:
    return "\n\n".join(
        f"[{w.id}]\nKey sentences: {' | '.join(w.hit_sentences)}\nFull passage: {w.text}"
        for w in windows)


def run_evidence(analysis: Analysis, retriever: Retriever | None = None) -> dict:
    retriever = retriever or Retriever()
    system = load_prompt("evidence")
    results = []

    for kind, query in build_queries(analysis):
        windows = retriever.search(query)
        entry = {"about": kind, "query": query, "findings": []}
        try:
            data = chat_json(system, f"QUESTION: {query}\n\nPASSAGES:\n{format_windows(windows)}",
                             temperature=0.1)
            raw = data.get("findings", [])
            entry["findings"] = [asdict(f) for f in verify(raw if isinstance(raw, list) else [], windows)]
        except ValueError as e:                      # model never produced valid JSON
            entry["error"] = str(e)
        results.append(entry)

    return {
        "claim": analysis.claim,
        "llm_model": settings.model,
        "embedding_model": settings.emb_model,
        "context_sentences": settings.context,
        "index_documents": {d: sha[:12] for d, sha in retriever.store.doc_hashes().items()},
        "evidence": results,
    }