import pytest

from climate_claims import llm
from climate_claims.config import Settings


class FakeResponse:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload or {}, text

    def json(self):
        return self._payload


def use(monkeypatch, **kw):
    cfg = Settings(**{"llm_provider": "openai", "llm_base_url": "", "llm_api_key": "k",
                      "llm_model": "m", **kw})
    monkeypatch.setattr(llm, "settings", cfg)


def capture(monkeypatch, responses):
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers, "json": json})
        return responses[min(len(calls), len(responses)) - 1]

    monkeypatch.setattr(llm.requests, "post", fake_post)
    return calls


OPENAI_OK = FakeResponse(payload={"choices": [{"message": {"content": '{"a": 1}'}}]})
ANTHROPIC_OK = FakeResponse(payload={"content": [{"type": "thinking", "thinking": "..."},
                                                  {"type": "text", "text": '{"a": '},
                                                  {"type": "text", "text": "1}"}]})


def test_openai_compatible_request_shape(monkeypatch):
    use(monkeypatch, llm_base_url="https://host/api")
    calls = capture(monkeypatch, [OPENAI_OK])
    assert llm.chat_json("sys", "usr", temperature=0.3) == {"a": 1}
    c = calls[0]
    assert c["url"] == "https://host/api/chat/completions"
    assert c["headers"] == {"Authorization": "Bearer k"}
    assert c["json"] == {"model": "m", "temperature": 0.3,
                         "messages": [{"role": "system", "content": "sys"},
                                      {"role": "user", "content": "usr"}]}


def test_openai_default_base_url(monkeypatch):
    use(monkeypatch)
    calls = capture(monkeypatch, [OPENAI_OK])
    llm.chat_json("s", "u")
    assert calls[0]["url"] == "https://api.openai.com/v1/chat/completions"


def test_anthropic_request_shape_and_text_blocks(monkeypatch):
    use(monkeypatch, llm_provider="anthropic")
    calls = capture(monkeypatch, [ANTHROPIC_OK])
    assert llm.chat_json("sys", "usr") == {"a": 1}
    c = calls[0]
    assert c["url"] == "https://api.anthropic.com/v1/messages"
    assert c["headers"] == {"x-api-key": "k", "anthropic-version": "2023-06-01"}
    assert c["json"]["system"] == "sys"
    assert c["json"]["messages"] == [{"role": "user", "content": "usr"}]
    assert c["json"]["max_tokens"] == llm.ANTHROPIC_MAX_TOKENS


def test_retries_without_temperature_when_model_rejects_it(monkeypatch):
    use(monkeypatch)
    calls = capture(monkeypatch, [FakeResponse(400, text="Unsupported value: 'temperature'"), OPENAI_OK])
    assert llm.chat_json("s", "u") == {"a": 1}
    assert "temperature" in calls[0]["json"] and "temperature" not in calls[1]["json"]


def test_other_http_errors_are_not_retried(monkeypatch):
    use(monkeypatch)
    calls = capture(monkeypatch, [FakeResponse(401, text="bad key")])
    with pytest.raises(llm.LLMError, match="401"):
        llm.chat_json("s", "u")
    assert len(calls) == 1


def test_missing_key_or_model_or_provider(monkeypatch):
    use(monkeypatch, llm_api_key="")
    with pytest.raises(SystemExit, match="LLM_API_KEY"):
        llm.chat_json("s", "u")
    use(monkeypatch, llm_model="")
    with pytest.raises(SystemExit, match="LLM_MODEL"):
        llm.chat_json("s", "u")
    use(monkeypatch, llm_provider="nope")
    with pytest.raises(SystemExit, match="LLM_PROVIDER"):
        llm.chat_json("s", "u")


def test_local_server_needs_no_key(monkeypatch):
    use(monkeypatch, llm_api_key="", llm_base_url="http://localhost:11434/v1")
    calls = capture(monkeypatch, [OPENAI_OK])
    llm.chat_json("s", "u")
    assert calls[0]["headers"] == {}


def test_think_blocks_are_stripped():
    assert llm._parse_json('<think>{"x": 0}</think> ok {"a": 2}') == {"a": 2}
