from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict

import requests

from ..analysis.plan import make_plan
from ..config import settings
from ..llm import chat_json, load_prompt
from ..retrieval.retriever import Retriever
from ..schemas import Analysis, EvidenceNeed, Window
from .dedupe import dedupe_findings
from .verify import verify
from ..sources import add_link


MAX_WINDOWS = 8       # passages shown to the model per evidence need


def build_queries(a: Analysis) -> list[tuple[str, str]]:
    queries = [("claim", a.claim)]
    for amb in a.ambiguities:
        queries.append(("ambiguity", f"{amb.term_or_relation}: " + "; ".join(amb.possible_meanings)))
    for h in a.hidden_assumptions:
        queries.append(("assumption", h))
    return queries


def basic_needs(a: Analysis) -> list[EvidenceNeed]:
    """Fallback when the plan cannot be made: one need per query, no support/refute description."""
    return [EvidenceNeed(f"N{i}", q, kind, q, "", "", [q])
            for i, (kind, q) in enumerate(build_queries(a), 1)]


def format_windows(windows: list[Window]) -> str:
    return "\n\n".join(
        f"[{w.id}]\nKey sentences: {' | '.join(w.hit_sentences)}\nFull passage: {w.text}"
        for w in windows)


def gather_windows(retriever: Retriever, need: EvidenceNeed, limit: int = MAX_WINDOWS) -> list[Window]:
    """Search with every query of the need; keep each passage once, best score first."""
    best: dict[str, Window] = {}
    for q in need.queries:
        for w in retriever.search(q):
            if w.id not in best or w.score > best[w.id].score:
                best[w.id] = w
    return sorted(best.values(), key=lambda w: -w.score)[:limit]


def _prompt(need: EvidenceNeed, windows: list[Window]) -> str:
    lines = [f"PROPOSITION: {need.proposition}"]
    if need.supporting:
        lines.append(f"A SOURCE SUPPORTING IT WOULD SAY: {need.supporting}")
    if need.refuting:
        lines.append(f"A SOURCE REFUTING IT WOULD SAY: {need.refuting}")
    return "\n".join(lines) + f"\n\nPASSAGES:\n{format_windows(windows)}"


def _ask(system: str, need: EvidenceNeed, windows: list[Window]) -> dict:
    """One LLM call + verification. Never raises: a failure is recorded in its own entry."""
    entry = {"about": need.origin, "need_id": need.id, "query": need.proposition,
             "supporting": need.supporting, "refuting": need.refuting,
             "queries": need.queries, "findings": []}
    try:
        data = chat_json(system, _prompt(need, windows), temperature=0.1)
        raw = data.get("findings", [])
        verified = verify(raw if isinstance(raw, list) else [], windows)
        entry["findings"] = [asdict(add_link(f)) for f in verified]
    except (ValueError, requests.RequestException) as e:   # bad JSON, timeout, network
        entry["error"] = str(e)
    return entry


def plan_needs(analysis: Analysis, retriever) -> tuple[list[EvidenceNeed], str | None]:
    """The evidence plan, or the basic queries (and the reason) if the model cannot make one."""
    try:
        return make_plan(analysis, list(retriever.store.doc_hashes())), None
    except (ValueError, requests.RequestException) as e:
        return basic_needs(analysis), f"Could not plan the evidence search, used basic queries ({e})"


def run_evidence(analysis: Analysis, retriever: Retriever | None = None, on_entry=None) -> dict:
    """Plan, retrieve, extract and verify evidence for the analysis.

    1. The plan turns the analysis into evidence needs (propositions + what supporting and
       refuting evidence would say + queries). If it fails, the basic queries are used.
    2. Retrieval runs sequentially in the calling thread (the index and the embedding model
       are not shared across threads); the slow LLM calls run in parallel (`settings.llm_workers`).

    `on_entry(entry, done, total)` is called from the calling thread so a caller (the web app)
    can show results as they arrive. Entries are always delivered in plan order (the claim
    first, then the implied argument, ambiguities, assumptions): an entry that finishes early
    waits for the ones before it. `done` counts needs already answered, so progress is never
    held back. The returned `evidence` list is in the same order. A failing need is recorded,
    not fatal.
    """
    retriever = retriever or Retriever()
    system = load_prompt("evidence")
    needs, plan_error = plan_needs(analysis, retriever)
    jobs = [(need, gather_windows(retriever, need)) for need in needs]
    total = len(jobs)

    results: list[dict | None] = [None] * total
    next_to_emit = 0
    with ThreadPoolExecutor(max_workers=max(1, settings.llm_workers)) as pool:
        futures = {pool.submit(_ask, system, need, windows): i for i, (need, windows) in enumerate(jobs)}
        for done, future in enumerate(as_completed(futures), 1):
            results[futures[future]] = future.result()
            while next_to_emit < total and results[next_to_emit] is not None:
                if on_entry:
                    on_entry(results[next_to_emit], done, total)
                next_to_emit += 1

    # collapse copies of one finding across documents *within* a need; the same quote can
    # legitimately appear under several needs (it may support one proposition and refute another)
    evidence = [dedupe_findings([e])[0] for e in results]
    return {
        "claim": analysis.claim,
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "embedding_model": settings.emb_model,
        "context_sentences": settings.context,
        "index_documents": {d: sha[:12] for d, sha in retriever.store.doc_hashes().items()},
        "plan": [asdict(n) for n in needs],
        "plan_error": plan_error,
        "evidence": evidence,
    }