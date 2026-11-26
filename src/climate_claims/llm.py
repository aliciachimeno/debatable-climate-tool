import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from .config import settings

PROMPTS_DIR = Path(__file__).parent / "prompts"

DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
}
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_MAX_TOKENS = 4096


class LLMError(requests.HTTPError):
    """The provider answered with an error (bad key, unknown model, quota ...).

    A requests exception on purpose: the pipeline and the web app already treat those as
    "the model could not answer" and keep going."""

    def __init__(self, status: int, body: str):
        super().__init__(f"LLM request failed (HTTP {status}): {body[:500]}")
        self.status, self.body = status, body


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def _is_local(url: str) -> bool:
    return urlparse(url).hostname in {"localhost", "127.0.0.1", "::1"}


def _post(url: str, headers: dict, body: dict) -> dict:
    resp = requests.post(url, headers=headers, json=body, timeout=settings.llm_timeout)
    if resp.status_code >= 400:
        raise LLMError(resp.status_code, resp.text)
    return resp.json()


def _openai_request(base: str, key: str, model: str, system: str, user: str,
                    temperature: float | None) -> str:
    body = {"model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    if temperature is not None:
        body["temperature"] = temperature
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    data = _post(f"{base}/chat/completions", headers, body)
    return data["choices"][0]["message"]["content"]


def _anthropic_request(base: str, key: str, model: str, system: str, user: str,
                       temperature: float | None) -> str:
    body = {"model": model, "max_tokens": ANTHROPIC_MAX_TOKENS, "system": system,
            "messages": [{"role": "user", "content": user}]}
    if temperature is not None:
        body["temperature"] = temperature
    headers = {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION}
    data = _post(f"{base}/v1/messages", headers, body)
    return "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")


REQUESTS = {"openai": _openai_request, "anthropic": _anthropic_request}


def _chat(system: str, user: str, temperature: float) -> str:
    provider = settings.llm_provider
    if provider not in REQUESTS:
        raise SystemExit(f"Unknown LLM_PROVIDER {provider!r}. Use one of: {', '.join(REQUESTS)}.")
    base = settings.llm_base_url or DEFAULT_BASE_URLS[provider]
    if not settings.llm_model:
        raise SystemExit("Set LLM_MODEL (see .env.example).")
    if not settings.llm_api_key and not (provider == "openai" and _is_local(base)):
        raise SystemExit("Set LLM_API_KEY (see .env.example).")

    send = REQUESTS[provider]
    args = (base, settings.llm_api_key, settings.llm_model, system, user)
    try:
        return send(*args, temperature)
    except LLMError as e:
        # Some models only accept their default temperature: retry once without it.
        if e.status == 400 and "temperature" in e.body.lower():
            return send(*args, None)
        raise


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
