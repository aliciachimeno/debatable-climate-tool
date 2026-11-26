// The "Language model" box: provider, base URL, API key and model.
// The key lives in sessionStorage (forgotten when the tab closes) unless the visitor opts in to remembering it.
import { PROVIDERS, complete, resolveConfig } from './providers.js';

const SETTINGS_KEY = 'debatable.settings';
const API_KEY_KEY = 'debatable.apiKey';

const safe = (fn, fallback) => { try { return fn(); } catch { return fallback; } };
const $ = (id) => document.getElementById(id);

function load() {
  const s = safe(() => JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}'), {});
  const store = s.remember ? localStorage : sessionStorage;
  return { provider: 'openai', baseUrl: '', model: '', remember: false, ...s,
           apiKey: safe(() => store.getItem(API_KEY_KEY), '') || '' };
}

function save(cfg) {
  const { apiKey, ...rest } = cfg;
  safe(() => localStorage.setItem(SETTINGS_KEY, JSON.stringify(rest)));
  safe(() => {
    localStorage.removeItem(API_KEY_KEY);
    sessionStorage.removeItem(API_KEY_KEY);
    (cfg.remember ? localStorage : sessionStorage).setItem(API_KEY_KEY, apiKey);
  });
}

const read = () => ({ provider: $('llm-provider').value, baseUrl: $('llm-baseUrl').value.trim(),
                      apiKey: $('llm-apiKey').value.trim(), model: $('llm-model').value.trim(),
                      remember: $('llm-remember').checked });

export function isReady(cfg) {
  try { resolveConfig(cfg); return true; } catch { return false; }
}

function refreshSummary() {
  const cfg = read();
  const ready = isReady(cfg);
  $('llm-dot').className = 'dot' + (ready ? ' on' : '');
  $('llm-summary').textContent = ready ? `${PROVIDERS[cfg.provider].label} · ${cfg.model}` : 'Language model';
  const preset = PROVIDERS[cfg.provider];
  $('llm-baseUrl').placeholder = preset.baseUrl || 'https://your-server/api';
  $('llm-help').textContent = preset.help;
}

/** Wires the box; returns {get, ready, open}. */
export function initSettings() {
  for (const [id, p] of Object.entries(PROVIDERS)) {
    const o = document.createElement('option');
    o.value = id; o.textContent = p.label;
    $('llm-provider').append(o);
  }
  const cfg = load();
  $('llm-provider').value = PROVIDERS[cfg.provider] ? cfg.provider : 'openai';
  $('llm-baseUrl').value = cfg.baseUrl;
  $('llm-apiKey').value = cfg.apiKey;
  $('llm-model').value = cfg.model;
  $('llm-remember').checked = cfg.remember;
  refreshSummary();

  $('llm-provider').addEventListener('change', () => { $('llm-baseUrl').value = ''; });
  $('llm-form').addEventListener('input', () => { save(read()); refreshSummary(); });
  $('llm-form').addEventListener('submit', (e) => e.preventDefault());

  $('llm-test').addEventListener('click', async () => {
    const out = $('llm-test-result');
    out.className = 'hint';
    out.textContent = 'Testing…';
    try {
      const text = await complete(read(), 'Reply with the single word: ok', 'ping', 0);
      out.className = 'hint ok';
      out.textContent = text.trim() ? 'Connected.' : 'Connected, but the model returned no text.';
    } catch (e) {
      out.className = 'hint err';
      out.textContent = e?.message ?? String(e);
    }
  });

  return {
    get: read,
    ready: () => isReady(read()),
    open: () => { $('llm').open = true; $('llm-apiKey').focus(); },
  };
}
