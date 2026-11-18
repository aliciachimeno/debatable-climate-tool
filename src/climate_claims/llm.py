import json
import re
from pathlib import Path

import requests

from .config import settings

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def _chat(system: str, user: str, temperature: float) -> str:
    if not settings.api_key or not settings.model:
        raise SystemExit("Set OPENWEBUI_API_KEY and OPENWEBUI_MODEL (see .env.example).")
    resp = requests.post(
        f"{settings.url}/api/chat/completions",
        headers={"Authorization": f"Bearer {settings.api_key}"},
        json={"model": settings.model, "temperature": temperature,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": user}]},
        timeout=settings.llm_timeout,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _parse_json(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)   # reasoning models
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"No JSON object in model output: {text[:200]!r}")
    return json.loads(text[start:end + 1])   # JSONDecodeError is a ValueError


def chat_json(system: str, user: str, temperature: float = 0.2, retries: int = 2) -> dict:
    """Call the model and return parsed JSON, retrying on invalid JSON or network timeouts."""
    for attempt in range(retries + 1):
        try:
            return _parse_json(_chat(system, user, temperature))
        except (ValueError, requests.Timeout, requests.ConnectionError):
            if attempt == retries:
                raise