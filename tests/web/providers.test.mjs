import test from 'node:test';
import assert from 'node:assert/strict';
import { complete, LLMError, resolveConfig } from '../../src/climate_claims/web/static/js/providers.js';
import { chatJson, parseJson, ModelOutputError } from '../../src/climate_claims/web/static/js/llm.js';

const reply = (status, body) => ({
  ok: status < 400, status, text: async () => (typeof body === 'string' ? body : JSON.stringify(body)),
});

function fakeFetch(...responses) {
  const calls = [];
  const fn = async (url, init) => {
    calls.push({ url, init, body: JSON.parse(init.body) });
    const r = responses[Math.min(calls.length, responses.length) - 1];
    if (r instanceof Error) throw r;
    return r;
  };
  fn.calls = calls;
  return fn;
}

const OPENAI_OK = reply(200, { choices: [{ message: { content: '{"a":1}' } }] });
const ANTHROPIC_OK = reply(200, { content: [{ type: 'thinking', thinking: '..' }, { type: 'text', text: '{"a":' }, { type: 'text', text: '1}' }] });
const cfg = (o = {}) => ({ provider: 'openai', baseUrl: '', apiKey: 'k', model: 'm', ...o });

test('openai-compatible request shape', async () => {
  const f = fakeFetch(OPENAI_OK);
  const out = await complete(cfg({ provider: 'custom', baseUrl: 'https://host/api/' }), 'sys', 'usr', 0.3, { fetchImpl: f });
  assert.equal(out, '{"a":1}');
  const c = f.calls[0];
  assert.equal(c.url, 'https://host/api/chat/completions');
  assert.equal(c.init.headers.authorization, 'Bearer k');
  assert.deepEqual(c.body, { model: 'm', temperature: 0.3,
    messages: [{ role: 'system', content: 'sys' }, { role: 'user', content: 'usr' }] });
});

test('preset base URLs', async () => {
  for (const [provider, url] of [['openai', 'https://api.openai.com/v1/chat/completions'],
                                 ['openrouter', 'https://openrouter.ai/api/v1/chat/completions']]) {
    const f = fakeFetch(OPENAI_OK);
    await complete(cfg({ provider }), 's', 'u', 0, { fetchImpl: f });
    assert.equal(f.calls[0].url, url);
  }
});

test('anthropic request shape, browser opt-in header and text blocks only', async () => {
  const f = fakeFetch(ANTHROPIC_OK);
  const out = await complete(cfg({ provider: 'anthropic' }), 'sys', 'usr', 0.2, { fetchImpl: f });
  assert.equal(out, '{"a":1}');
  const c = f.calls[0];
  assert.equal(c.url, 'https://api.anthropic.com/v1/messages');
  assert.equal(c.init.headers['x-api-key'], 'k');
  assert.equal(c.init.headers['anthropic-version'], '2023-06-01');
  assert.equal(c.init.headers['anthropic-dangerous-direct-browser-access'], 'true');
  assert.equal(c.init.headers.authorization, undefined);
  assert.equal(c.body.system, 'sys');
  assert.deepEqual(c.body.messages, [{ role: 'user', content: 'usr' }]);
  assert.equal(c.body.max_tokens, 4096);
});

test('retries once without temperature when the model rejects it', async () => {
  const f = fakeFetch(reply(400, "Unsupported value: 'temperature'"), OPENAI_OK);
  assert.equal(await complete(cfg(), 's', 'u', 0.5, { fetchImpl: f }), '{"a":1}');
  assert.ok('temperature' in f.calls[0].body);
  assert.ok(!('temperature' in f.calls[1].body));
});

test('other HTTP errors surface with status and are not retried', async () => {
  const f = fakeFetch(reply(401, 'bad key'));
  await assert.rejects(complete(cfg(), 's', 'u', 0, { fetchImpl: f }), (e) => e instanceof LLMError && e.status === 401 && /bad key/.test(e.message));
  assert.equal(f.calls.length, 1);
});

test('network failure explains CORS / URL', async () => {
  const f = fakeFetch(new TypeError('Failed to fetch'));
  await assert.rejects(complete(cfg(), 's', 'u', 0, { fetchImpl: f }), (e) => e.status === 0 && /CORS/.test(e.message));
});

test('config validation', () => {
  assert.throws(() => resolveConfig(cfg({ apiKey: '' })), /API key/);
  assert.throws(() => resolveConfig(cfg({ model: ' ' })), /model/i);
  assert.throws(() => resolveConfig(cfg({ provider: 'custom' })), /base URL/);
  assert.throws(() => resolveConfig(cfg({ provider: 'custom', baseUrl: 'not a url' })), /not a valid URL/);
  assert.doesNotThrow(() => resolveConfig(cfg({ provider: 'custom', baseUrl: 'http://localhost:11434/v1', apiKey: '' })));
  assert.throws(() => resolveConfig(cfg({ provider: 'anthropic', apiKey: '' })), /API key/);
});

test('local server request sends no authorization header', async () => {
  const f = fakeFetch(OPENAI_OK);
  await complete(cfg({ provider: 'custom', baseUrl: 'http://localhost:11434/v1', apiKey: '' }), 's', 'u', 0, { fetchImpl: f });
  assert.equal(f.calls[0].init.headers.authorization, undefined);
});

test('parseJson strips think blocks and surrounding prose', () => {
  assert.deepEqual(parseJson('<think>{"x":0}</think> here: {"a":2} done'), { a: 2 });
  assert.throws(() => parseJson('no json'), ModelOutputError);
  assert.throws(() => parseJson('{broken'), ModelOutputError);
});

test('chatJson retries bad output then succeeds, and does not retry auth errors', async () => {
  const f = fakeFetch(reply(200, { choices: [{ message: { content: 'sorry' } }] }), OPENAI_OK);
  assert.deepEqual(await chatJson(cfg(), 's', 'u', { fetchImpl: f }), { a: 1 });
  assert.equal(f.calls.length, 2);
  const g = fakeFetch(reply(401, 'no'));
  await assert.rejects(chatJson(cfg(), 's', 'u', { fetchImpl: g }), LLMError);
  assert.equal(g.calls.length, 1);
});
