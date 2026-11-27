// Port of src/climate_claims/{analysis,evidence}: same prompts, same checks, same result shape
// as the Python pipeline, so the interface can show either.
import { chatJson, ModelOutputError } from './llm.js';
import { LLMError } from './providers.js';
import { forSpan } from './provenance.js';

export const CLAIM_TYPES = new Set(['descriptive_factual', 'causal_attribution', 'predictive', 'policy_value']);
export const NEED_ORIGINS = ['claim', 'ambiguity', 'assumption', 'implied_argument'];   // also the display order
export const STANCES = ['supports', 'refutes', 'context'];
export const MAX_WINDOWS = 8;         // passages shown to the model per evidence need
export const MAX_NEEDS = 10;
export const MAX_QUOTE_WORDS = 40;
export const DEFAULT_WORKERS = 4;     // parallel LLM calls

const isObject = (x) => x !== null && typeof x === 'object' && !Array.isArray(x);

// ---------- stage 1: analysis ----------
export function validateAnalysis(d) {
  const bad = (what) => new ModelOutputError(`LLM output missing or invalid field: ${what}`);
  const text = (k) => { if (typeof d?.[k] !== 'string') throw bad(k); return d[k]; };
  const m = d?.type_mismatch;
  if (!isObject(m)) throw bad('type_mismatch');
  if (!Array.isArray(d.ambiguities)) throw bad('ambiguities');
  if (!Array.isArray(d.hidden_assumptions)) throw bad('hidden_assumptions');
  const a = {
    claim_type: text('claim_type'),
    type_reason: text('type_reason'),
    literal_meaning: text('literal_meaning'),
    implied_argument: text('implied_argument'),
    ambiguities: d.ambiguities.map((x) => {
      if (typeof x?.term_or_relation !== 'string' || !Array.isArray(x.possible_meanings)) throw bad('ambiguities');
      return { term_or_relation: x.term_or_relation, possible_meanings: x.possible_meanings.map(String) };
    }),
    hidden_assumptions: d.hidden_assumptions.map(String),
    type_mismatch: {
      detected: Boolean(m.detected), premise_type: String(m.premise_type),
      conclusion_type: String(m.conclusion_type), explanation: String(m.explanation),
    },
  };
  if (!CLAIM_TYPES.has(a.claim_type)) throw new ModelOutputError(`Unknown claim_type: ${a.claim_type}`);
  return a;
}

export async function analyze(cfg, claim, prompts, { signal, fetchImpl } = {}) {
  const data = await chatJson(cfg, prompts.analyze, `Claim: ${claim}`,
                              { validate: validateAnalysis, signal, fetchImpl });
  return { claim, ...data };
}

// ---------- stage 2a: evidence plan ----------
export function buildQueries(a) {
  const queries = [['claim', a.claim]];
  for (const amb of a.ambiguities) queries.push(['ambiguity', `${amb.term_or_relation}: ${amb.possible_meanings.join('; ')}`]);
  for (const h of a.hidden_assumptions) queries.push(['assumption', h]);
  return queries;
}

/** Fallback when the plan cannot be made: one need per query, no support/refute description. */
export function basicNeeds(a) {
  return buildQueries(a).map(([kind, q], i) => ({
    id: `N${i + 1}`, proposition: q, origin: kind, source_text: q, supporting: '', refuting: '', queries: [q],
  }));
}

function needFromDict(d) {
  if (!isObject(d) || d.proposition == null || !Array.isArray(d.queries)) return null;
  const proposition = String(d.proposition).trim();
  const queries = [...new Set(d.queries.filter((q) => typeof q === 'string' && q.trim()).map((q) => q.trim()))];
  if (!proposition || !NEED_ORIGINS.includes(d.origin) || !queries.length) return null;
  return {
    id: '', proposition, origin: d.origin, source_text: String(d.source_text ?? '').trim(),
    supporting: String(d.supporting ?? '').trim(), refuting: String(d.refuting ?? '').trim(),
    queries: queries.slice(0, 4),
  };
}

export function parseNeeds(data) {
  const raw = isObject(data) ? data.needs : null;
  if (!Array.isArray(raw)) throw new ModelOutputError("The plan has no 'needs' list");
  const needs = raw.map(needFromDict).filter(Boolean);             // malformed items are skipped
  if (!needs.length) throw new ModelOutputError('The plan contains no valid evidence needs');
  needs.sort((a, b) => NEED_ORIGINS.indexOf(a.origin) - NEED_ORIGINS.indexOf(b.origin));   // stable: claim first
  return needs.slice(0, MAX_NEEDS).map((n, i) => ({ ...n, id: `N${i + 1}` }));
}

export async function makePlan(cfg, analysis, documents, prompts, { signal, fetchImpl } = {}) {
  const payload = { analysis, available_documents: documents };
  return chatJson(cfg, prompts.plan, JSON.stringify(payload, null, 1),
                  { temperature: 0.2, validate: parseNeeds, signal, fetchImpl });
}

/** The evidence plan, or the basic queries (and the reason) if the model cannot make one. */
export async function planNeeds(cfg, analysis, documents, prompts, opts) {
  try {
    return { needs: await makePlan(cfg, analysis, documents, prompts, opts), planError: null };
  } catch (e) {
    if (!(e instanceof ModelOutputError || e instanceof LLMError)) throw e;
    return { needs: basicNeeds(analysis), planError: `Could not plan the evidence search, used basic queries (${e.message})` };
  }
}

// ---------- stage 2b: retrieve, extract, verify ----------
export const windowId = (w) => `${w.doc}:${w.lo}-${w.hi}`;
export const windowText = (w) => w.sentences.map(([, t]) => t).join(' ');

export function formatWindows(windows) {
  return windows.map((w) =>
    `[${windowId(w)}]\nKey sentences: ${w.hitSentences.join(' | ')}\nFull passage: ${windowText(w)}`).join('\n\n');
}

/** Search with every query of the need; keep each passage once, best score first. */
export async function gatherWindows(retriever, need, limit = MAX_WINDOWS) {
  const best = new Map();
  for (const q of need.queries) {
    for (const w of await retriever.search(q)) {
      const id = windowId(w);
      if (!best.has(id) || w.score > best.get(id).score) best.set(id, w);
    }
  }
  return [...best.values()].sort((a, b) => b.score - a.score).slice(0, limit);
}

export function needPrompt(need, windows) {
  const lines = [`PROPOSITION: ${need.proposition}`];
  if (need.supporting) lines.push(`A SOURCE SUPPORTING IT WOULD SAY: ${need.supporting}`);
  if (need.refuting) lines.push(`A SOURCE REFUTING IT WOULD SAY: ${need.refuting}`);
  return `${lines.join('\n')}\n\nPASSAGES:\n${formatWindows(windows)}`;
}

export const norm = (s) => s.toLowerCase().split(/\s+/).filter(Boolean).join(' ');

/** Positions [first, last] in window.sentences of the sentences `quote` spans, or null. */
function spanOf(quote, window) {
  const q = norm(quote);
  if (!q) return null;
  const sents = window.sentences.map(([, t]) => norm(t));
  const starts = [];
  let pos = 0;
  for (const s of sents) { starts.push(pos); pos += s.length + 1; }
  const at = sents.join(' ').indexOf(q);
  if (at < 0) return null;
  const end = at + q.length - 1;
  const lastStartBefore = (p) => starts.reduce((acc, s, i) => (s <= p ? i : acc), 0);
  return [lastStartBefore(at), lastStartBefore(end)];
}

/** Pages spanned by `quote` if it appears verbatim in the window, else null. */
export function locate(quote, window) {
  const span = spanOf(quote, window);
  if (!span) return null;
  const pages = new Set();
  for (let i = span[0]; i <= span[1]; i++) pages.add(window.sentences[i][0]);
  return [...pages].sort((x, y) => x - y);
}

/** [first, last] sentence index (in the document) of the quote, or null. */
export function locateSpan(quote, window) {
  const span = spanOf(quote, window);
  return span ? [window.lo + span[0], window.lo + span[1]] : null;
}

const NUMBER = /\d+(?:[.,]\d+)?/g;
/** Every number in the statement must also appear in the quote (catches paraphrase drift). */
export function numbersSupported(statement, quote) {
  const inQuote = new Set(quote.match(NUMBER) ?? []);
  return (statement.match(NUMBER) ?? []).every((n) => inQuote.has(n));
}

// Strength of evidence, read from the quote itself (no LLM).
const LIKELIHOOD = /\b(exceptionally unlikely|extremely unlikely|very unlikely|unlikely|virtually certain|extremely likely|very likely|more likely than not|about as likely as not|likely)\b/i;
const CONFIDENCE = /\b(very high|high|medium|low|very low) confidence\b/i;
export function strength(quote) {
  const lik = LIKELIHOOD.exec(quote), conf = CONFIDENCE.exec(quote);
  return {
    likelihood: lik ? lik[1].toLowerCase() : null,
    confidence: conf ? conf[1].toLowerCase() : null,
    stated_as_fact: quote.toLowerCase().includes('unequivocal'),
  };
}

/** Keep only findings whose quote literally appears in the cited window, is short enough,
 *  and whose statement adds no numbers the quote lacks. */
export function verify(raw, windows) {
  const byId = new Map(windows.map((w) => [windowId(w), w]));
  const good = [];
  for (const f of raw) {
    if (!isObject(f)) continue;
    const w = byId.get(f.passage_id);
    const quote = String(f.quote ?? ''), statement = String(f.statement ?? '');
    if (!(w && statement) || quote.split(/\s+/).filter(Boolean).length > MAX_QUOTE_WORDS) continue;
    if (!numbersSupported(statement, quote)) continue;
    const pages = locate(quote, w);
    if (!pages) continue;
    good.push({
      statement, quote, document: w.doc, pages, passage_id: windowId(w),
      label: '', url: '', ...strength(quote),
      also_in: [], stance: STANCES.includes(f.stance) ? f.stance : null,
      span: locateSpan(quote, w), provenance: null,
    });
  }
  return good;
}

/** What the quote points to (papers, sections, figures), from provenance.json when it is there. */
export function addProvenance(finding, provenance, sources) {
  if (provenance && finding.span) finding.provenance = forSpan(provenance, sources, finding.document, ...finding.span);
  return finding;
}

/** Label and link (to the cited page) from sources.json. */
export function addLink(finding, sources) {
  const info = sources?.[finding.document] ?? {};
  finding.label = info.label ?? finding.document;
  finding.url = info.url ? `${info.url}#page=${finding.pages[0]}` : '';
  return finding;
}

// ---------- collapse copies of one finding across documents (see evidence/dedupe.py) ----------
const RANKS = [[/chapter|_ch\d/i, 0], [/(^|[_\W])TS([_\W]|$)|technical.?summary/i, 1],
               [/SYR|synthesis/i, 3], [/SPM|summary.?for.?policy/i, 2]];   // SYR before SPM: SYR_SPM is a synthesis

export function sourceRank(doc) {
  for (const [pattern, rank] of RANKS) if (pattern.test(doc)) return rank;
  return 1;
}

export function dedupeFindings(entries) {
  const groups = new Map();
  entries.forEach((e, ei) => e.findings.forEach((f, fi) => {
    const key = norm(f.quote);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push([ei, fi]);
  }));

  const drop = new Set();
  for (const members of groups.values()) {
    if (members.length === 1) continue;
    const rank = (m) => sourceRank(entries[m[0]].findings[m[1]].document);
    const keep = [...members].sort((a, b) => rank(a) - rank(b) || a[0] - b[0] || a[1] - b[1])[0];
    const primary = entries[keep[0]].findings[keep[1]];
    const seen = new Set([`${primary.document}|${primary.pages}`]);
    for (const m of members) {
      if (m === keep) continue;
      const f = entries[m[0]].findings[m[1]];
      const key = `${f.document}|${f.pages}`;
      if (!seen.has(key)) {
        seen.add(key);
        (primary.also_in ??= []).push({ document: f.document, pages: f.pages });
      }
      drop.add(`${m[0]}:${m[1]}`);
    }
  }
  return entries.map((e, ei) => ({ ...e, findings: e.findings.filter((_, fi) => !drop.has(`${ei}:${fi}`)) }));
}

// ---------- the whole evidence run ----------
async function ask(cfg, system, need, windows, sources, { signal, fetchImpl, provenance }) {
  const entry = { about: need.origin, need_id: need.id, query: need.proposition,
                  supporting: need.supporting, refuting: need.refuting, queries: need.queries, findings: [] };
  try {
    const data = await chatJson(cfg, system, needPrompt(need, windows), { temperature: 0.1, signal, fetchImpl });
    const verified = verify(Array.isArray(data.findings) ? data.findings : [], windows);
    entry.findings = verified.map((f) => addProvenance(addLink(f, sources), provenance, sources));
  } catch (e) {
    if (!(e instanceof ModelOutputError || e instanceof LLMError)) throw e;     // aborts and bugs propagate
    entry.error = e.message;                                                     // a failing need is recorded, not fatal
  }
  return entry;
}

/** Plan, retrieve, extract and verify. `onEntry(entry, done, total)` is called as results arrive,
 *  always in plan order (an entry that finishes early waits for the ones before it). */
export async function runEvidence(cfg, analysis, retriever, prompts, sources = {},
                                  { signal, fetchImpl, onEntry, workers = DEFAULT_WORKERS, provenance = null } = {}) {
  const io = { signal, fetchImpl, provenance };
  const documents = retriever.meta.docs.map((d) => d.name);
  const { needs, planError } = await planNeeds(cfg, analysis, documents, prompts, io);

  const jobs = [];                                     // retrieval is sequential, the slow LLM calls are not
  for (const need of needs) jobs.push([need, await gatherWindows(retriever, need)]);

  const total = jobs.length;
  const results = new Array(total).fill(null);
  let nextJob = 0, nextEmit = 0, done = 0;
  const worker = async () => {
    for (let i = nextJob++; i < total; i = nextJob++) {
      results[i] = await ask(cfg, prompts.evidence, jobs[i][0], jobs[i][1], sources, io);
      done++;
      while (nextEmit < total && results[nextEmit]) {
        const entry = results[nextEmit++];       // (not inside `onEntry?.(...)`: optional calls skip their arguments)
        onEntry?.(entry, done, total);
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(Math.max(1, workers), total) }, worker));

  // collapse copies of one finding across documents *within* a need; the same quote can legitimately
  // appear under several needs (it may support one proposition and refute another)
  const evidence = results.map((e) => dedupeFindings([e])[0]);
  return {
    claim: analysis.claim,
    llm_provider: cfg.provider,
    llm_model: cfg.model,
    embedding_model: retriever.meta.emb_model,
    context_sentences: retriever.meta.context,
    index_documents: Object.fromEntries(retriever.meta.docs.map((d) => [d.name, d.sha])),
    plan: needs,
    plan_error: planError,
    evidence,
  };
}
