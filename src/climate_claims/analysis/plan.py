"""Intermediate step between the analysis and the evidence search.

The analysis says what the claim means. The plan turns that into evidence needs: checkable
propositions, what a supporting and a refuting source would look like, and search queries
written in the documents' vocabulary.
"""
import dataclasses
import json

from ..llm import chat_json, load_prompt
from ..schemas import NEED_ORIGINS, Analysis, EvidenceNeed

MAX_NEEDS = 10


def parse_needs(data: dict) -> list[EvidenceNeed]:
    raw = data.get("needs") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        raise ValueError("The plan has no 'needs' list")
    needs = []
    for item in raw:
        try:
            needs.append(EvidenceNeed.from_dict(item))
        except (ValueError, AttributeError):          # skip malformed items, keep the rest
            continue
    if not needs:
        raise ValueError("The plan contains no valid evidence needs")
    needs.sort(key=lambda n: NEED_ORIGINS.index(n.origin))            # stable: claim first
    return [dataclasses.replace(n, id=f"N{i}") for i, n in enumerate(needs[:MAX_NEEDS], 1)]


def make_plan(analysis: Analysis, documents: list[str]) -> list[EvidenceNeed]:
    payload = {"analysis": analysis.to_dict(), "available_documents": documents}
    data = chat_json(load_prompt("plan"), json.dumps(payload, ensure_ascii=False, indent=1),
                     temperature=0.2)
    return parse_needs(data)