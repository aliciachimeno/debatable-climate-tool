// One function, `complete()`, talks to any supported LLM provider straight from the browser.
// "openai" kind  = POST {base}/chat/completions  (OpenAI, OpenRouter, Open WebUI, Ollama, vLLM, LM Studio...)
// "anthropic" kind = POST {base}/v1/messages     (Claude API)

export const ANTHROPIC_VERSION = '2023-06-01';
export const ANTHROPIC_MAX_TOKENS = 4096;
export const REQUEST_TIMEOUT_MS = 600_000;

export const PROVIDERS = {
  openai: {
    label: 'OpenAI', kind: 'openai', baseUrl: 'https://api.openai.com/v1',
    help: 'Use a model id from your OpenAI account.',
  },
  anthropic: {
    label: 'Anthropic', kind: 'anthropic', baseUrl: 'https://api.anthropic.com',
    help: 'Use a Claude model id from your Anthropic account.',
  },
  custom: {
    label: 'Gepeto', kind: 'gepeto', baseUrl: '',
    help: 'Enter everything before /chat/completions. Open WebUI: https://gepeto.bsc.es/api. ' +
          'Ollama: http://localhost:11434/v1. The server must allow requests from this page (CORS), ' +
          'and be reachable from your browser.',
  },
};

export class LLMError extends Error {
  constructor(status, body, message) {
    super(message ?? `LLM request failed (HTTP ${status}): ${String(body).slice(0, 500)}`);
    this.name = 'LLMError';
    this.status = status;       // 0 = the request never got an answer (network, CORS, bad URL)
    this.body = String(body);
  }
}

const isLocal = (url) => {
  try { return ['localhost', '127.0.0.1', '[::1]'].includes(new URL(url).hostname); }
  catch { return false; }
};

/** Validate the settings object {provider, baseUrl, apiKey, model}; returns {kind, base}. */
export function resolveConfig(cfg) {
  const preset = PROVIDERS[cfg.provider];
  if (!preset) throw new LLMError(0, '', `Unknown provider "${cfg.provider}".`);
  const base = (cfg.baseUrl || preset.baseUrl || '').trim().replace(/\/+$/, '');
  if (!base) throw new LLMError(0, '', 'Enter the base URL of your server.');
  try { new URL(base); } catch { throw new LLMError(0, '', `"${base}" is not a valid URL.`); }
  if (!cfg.model?.trim()) throw new LLMError(0, '', 'Enter a model name.');
  if (!cfg.apiKey?.trim() && !(preset.kind === 'openai' && isLocal(base))) {
    throw new LLMError(0, '', 'Enter your API key.');
  }
  return { kind: preset.kind, base };
}

async function post(url, headers, body, { signal, fetchImpl }) {
  let resp;
  try {
    resp = await fetchImpl(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json', ...headers },
      body: JSON.stringify(body),
      signal: AbortSignal.any([signal, AbortSignal.timeout(REQUEST_TIMEOUT_MS)].filter(Boolean)),
    });
  } catch (e) {
    if (e?.name === 'AbortError' || e?.name === 'TimeoutError') throw e;
    throw new LLMError(0, e, `Could not reach ${new URL(url).origin}. Check the base URL and your ` +
      'connection, and that the server allows requests from web pages (CORS).');
  }
  const text = await resp.text();
  if (!resp.ok) throw new LLMError(resp.status, text);
  try { return JSON.parse(text); }
  catch { throw new LLMError(resp.status, text, 'The server did not return JSON. Check the base URL.'); }
}

async function openaiRequest({ base, cfg, system, user, temperature, ...io }) {
  const body = {
    model: cfg.model.trim(),
    messages: [{ role: 'system', content: system }, { role: 'user', content: user }],
  };
  if (temperature != null) body.temperature = temperature;
  const headers = cfg.apiKey?.trim() ? { authorization: `Bearer ${cfg.apiKey.trim()}` } : {};
  const data = await post(`${base}/chat/completions`, headers, body, io);
  return data.choices?.[0]?.message?.content ?? '';
}

async function anthropicRequest({ base, cfg, system, user, temperature, ...io }) {
  const body = {
    model: cfg.model.trim(), max_tokens: ANTHROPIC_MAX_TOKENS, system,
    messages: [{ role: 'user', content: user }],
  };
  if (temperature != null) body.temperature = temperature;
  const headers = {
    'x-api-key': cfg.apiKey.trim(),
    'anthropic-version': ANTHROPIC_VERSION,
    // Anthropic requires this opt-in for calls made from a browser (the key is the user's own).
    'anthropic-dangerous-direct-browser-access': 'true',
  };
  const data = await post(`${base}/v1/messages`, headers, body, io);
  return (data.content ?? []).filter((b) => b.type === 'text').map((b) => b.text).join('');
}

const REQUESTS = { openai: openaiRequest, anthropic: anthropicRequest };

/** Send one system+user prompt, get the model's text back. */
export async function complete(cfg, system, user, temperature = 0.2,
                               { signal, fetchImpl = globalThis.fetch.bind(globalThis) } = {}) {
  const { kind, base } = resolveConfig(cfg);
  const send = (temp) => REQUESTS[kind]({ base, cfg, system, user, temperature: temp, signal, fetchImpl });
  try {
    return await send(temperature);
  } catch (e) {
    // Some models only accept their default temperature: retry once without it.
    if (e instanceof LLMError && e.status === 400 && /temperature/i.test(e.body)) return send(null);
    throw e;
  }
}
