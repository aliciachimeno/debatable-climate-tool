from ..llm import chat_json, load_prompt
from ..schemas import Analysis


def analyze(claim: str) -> Analysis:
    data = chat_json(load_prompt("analyze"), f"Claim: {claim}")
    return Analysis.from_dict({**data, "claim": claim})