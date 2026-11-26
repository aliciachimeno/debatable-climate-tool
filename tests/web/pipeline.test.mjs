import test from 'node:test';
import assert from 'node:assert/strict';
import {
  locate, verify, strength, validateAnalysis, buildQueries, basicNeeds, parseNeeds, formatWindows, windowId,
  dedupeFindings, sourceRank, gatherWindows, needPrompt, addLink, runEvidence, analyze,
} from '../../src/climate_claims/web/static/js/pipeline.js';

const win = () => ({ doc: 'doc.pdf', lo: 0, hi: 2, score: 0.9, hitSentences: ['Gamma delta.'],
  sentences: [[1, 'Alpha beta.'], [1, 'Gamma delta.'], [2, 'Epsilon zeta.']] });

// ---- same cases as tests/test_verify.py ----
test('locate: exact, spanning pages, case/whitespace, altered', () => {
  assert.deepEqual(locate('Gamma delta.', win()), [1]);
  assert.deepEqual(locate('Gamma delta. Epsilon zeta.', win()), [1, 2]);
  assert.deepEqual(locate('gamma   DELTA.', win()), [1]);
  assert.equal(locate('Gamma delta changed.', win()), null);
  assert.equal(locate('', win()), null);
});

test('verify keeps only findings whose quote is in the cited window', () => {
  const w = win();
  const out = verify([
    { statement: 'sa', passage_id: windowId(w), quote: 'Gamma delta.', stance: 'refutes' },
    { statement: 'sb', passage_id: windowId(w), quote: 'made up' },
    { statement: 'sc', passage_id: 'other:0-1', quote: 'Gamma delta.' },
    { statement: '', passage_id: windowId(w), quote: 'Gamma delta.' },
    'junk', null,
  ], [w]);
  assert.equal(out.length, 1);
  assert.deepEqual({ ...out[0] }, { statement: 'sa', quote: 'Gamma delta.', document: 'doc.pdf', pages: [1],
    passage_id: 'doc.pdf:0-2', label: '', url: '', likelihood: null, confidence: null, stated_as_fact: false,
    also_in: [], stance: 'refutes' });
});

test('invalid stance falls back to null', () => {
  const w = win();
  const [f] = verify([{ statement: 's', passage_id: windowId(w), quote: 'Gamma delta.', stance: 'banana' }], [w]);
  assert.equal(f.stance, null);
});

test('long quote rejected', () => {
  const words = Array.from({ length: 41 }, (_, i) => `w${i}`).join(' ');
  const w = { doc: 'd.pdf', lo: 0, hi: 0, score: 1, hitSentences: [words], sentences: [[1, words]] };
  assert.deepEqual(verify([{ statement: 's', passage_id: windowId(w), quote: words }], [w]), []);
});

test('numbers in the statement must be in the quote', () => {
  const t = 'Warming reached 1.1 degrees.';
  const w = { doc: 'd.pdf', lo: 0, hi: 0, score: 1, hitSentences: [t], sentences: [[1, t]] };
  assert.equal(verify([{ statement: 'It reached 1.1 degrees.', passage_id: windowId(w), quote: t }], [w]).length, 1);
  assert.deepEqual(verify([{ statement: 'It reached 1.5 degrees.', passage_id: windowId(w), quote: t }], [w]), []);
});

test('strength is extracted from the quote', () => {
  assert.equal(strength('It is unequivocal that human influence has warmed the atmosphere.').stated_as_fact, true);
  assert.deepEqual(strength('It is extremely likely that humans caused it (very high confidence).'),
    { likelihood: 'extremely likely', confidence: 'very high', stated_as_fact: false });
  assert.deepEqual(strength('Warming was observed.'), { likelihood: null, confidence: null, stated_as_fact: false });
  assert.equal(strength('It is very unlikely that this occurred.').likelihood, 'very unlikely');
});

// ---- same cases as tests/test_dedupe.py ----
const finding = (doc, pages, quote = 'It is unequivocal that human influence has warmed the atmosphere.') =>
  ({ statement: 's', quote, document: doc, pages, passage_id: `${doc}:0-1` });

test('source rank prefers chapters over summaries', () => {
  const ranks = ['IPCC_AR6_WGI_Chapter03.pdf', 'IPCC_AR6_WGI_TS.pdf', 'IPCC_AR6_WGI_SPM.pdf', 'IPCC_AR6_SYR_SPM.pdf'].map(sourceRank);
  assert.deepEqual(ranks, [0, 1, 2, 3]);
});

test('duplicates collapse to the chapter', () => {
  const entries = [
    { about: 'claim', query: 'q1', findings: [finding('IPCC_AR6_SYR_SPM.pdf', [11])] },
    { about: 'assumption', query: 'q2', findings: [finding('IPCC_AR6_WGI_Chapter03.pdf', [3]), finding('IPCC_AR6_WGI_Chapter01.pdf', [26])] },
  ];
  const out = dedupeFindings(entries);
  const kept = out.flatMap((e) => e.findings);
  assert.equal(kept.length, 1);
  assert.match(kept[0].document, /^IPCC_AR6_WGI_Chapter0/);
  assert.ok(kept[0].also_in.some((a) => a.document === 'IPCC_AR6_SYR_SPM.pdf'));
  assert.deepEqual(out[0].findings, []);
});

test('distinct quotes are kept', () => {
  const entries = [{ about: 'claim', query: 'q', findings: [finding('a.pdf', [1], 'One thing.'), finding('a.pdf', [2], 'Another thing.')] }];
  assert.equal(dedupeFindings(entries)[0].findings.length, 2);
});

// ---- analysis + plan ----
const ANALYSIS = {
  claim_type: 'descriptive_factual', type_reason: 'r', literal_meaning: 'l', implied_argument: 'i',
  ambiguities: [{ term_or_relation: 'always', possible_meanings: ['a', 'b'] }],
  hidden_assumptions: ['h1', 'h2'],
  type_mismatch: { detected: true, premise_type: 'p', conclusion_type: 'c', explanation: 'e' },
};

test('validateAnalysis accepts good output and rejects bad', () => {
  assert.equal(validateAnalysis(ANALYSIS).claim_type, 'descriptive_factual');
  assert.throws(() => validateAnalysis({ ...ANALYSIS, claim_type: 'nope' }), /Unknown claim_type/);
  assert.throws(() => validateAnalysis({ ...ANALYSIS, ambiguities: undefined }), /ambiguities/);
  assert.throws(() => validateAnalysis({ ...ANALYSIS, type_mismatch: null }), /type_mismatch/);
});

test('queries, basic needs and prompt layout match the Python ones', () => {
  const a = { claim: 'C', ...ANALYSIS };
  assert.deepEqual(buildQueries(a), [['claim', 'C'], ['ambiguity', 'always: a; b'], ['assumption', 'h1'], ['assumption', 'h2']]);
  assert.deepEqual(basicNeeds(a).map((n) => [n.id, n.origin, n.queries]), [
    ['N1', 'claim', ['C']], ['N2', 'ambiguity', ['always: a; b']], ['N3', 'assumption', ['h1']], ['N4', 'assumption', ['h2']]]);
  assert.equal(formatWindows([win()]), '[doc.pdf:0-2]\nKey sentences: Gamma delta.\nFull passage: Alpha beta. Gamma delta. Epsilon zeta.');
  assert.equal(needPrompt({ proposition: 'P', supporting: 'S', refuting: '' }, [win()]),
    'PROPOSITION: P\nA SOURCE SUPPORTING IT WOULD SAY: S\n\nPASSAGES:\n' + formatWindows([win()]));
});

test('parseNeeds sorts by origin, skips malformed items, numbers and caps queries', () => {
  const needs = parseNeeds({ needs: [
    { origin: 'assumption', proposition: ' B ', supporting: 's', refuting: 'r', queries: ['q1', 'q1', ' q2 ', 3, 'q3', 'q4', 'q5'] },
    { origin: 'claim', proposition: 'A', queries: ['qa'] },
    { origin: 'nonsense', proposition: 'X', queries: ['q'] },
    { origin: 'claim', proposition: 'no queries', queries: [] },
    'junk',
  ] });
  assert.deepEqual(needs.map((n) => [n.id, n.origin, n.proposition]), [['N1', 'claim', 'A'], ['N2', 'assumption', 'B']]);
  assert.deepEqual(needs[1].queries, ['q1', 'q2', 'q3', 'q4']);
  assert.throws(() => parseNeeds({}), /no 'needs'/);
  assert.throws(() => parseNeeds({ needs: [] }), /no valid/);
});

test('addLink uses label and the cited page', () => {
  const f = addLink({ document: 'd.pdf', pages: [7, 8] }, { 'd.pdf': { label: 'Report D', url: 'https://x.org/d.pdf' } });
  assert.deepEqual([f.label, f.url], ['Report D', 'https://x.org/d.pdf#page=7']);
  const g = addLink({ document: 'z.pdf', pages: [1] }, {});
  assert.deepEqual([g.label, g.url], ['z.pdf', '']);
});

// ---- gatherWindows + the whole run (mirrors tests/test_evidence_parallel.py) ----
const OPENAI_CFG = { provider: 'openai', baseUrl: '', apiKey: 'k', model: 'm' };
const content = (obj) => ({ ok: true, status: 200, text: async () => JSON.stringify({ choices: [{ message: { content: typeof obj === 'string' ? obj : JSON.stringify(obj) } }] }) });
const prompts = { analyze: 'A', plan: 'P', evidence: 'E' };
const makeRetriever = () => ({
  meta: { emb_model: 'x', context: 7, docs: [{ name: 'doc.pdf', sha: 'abc' }] },
  search: async (q) => [{ ...win(), score: q === 'low' ? 0.1 : 0.9 }],
});

test('gatherWindows keeps each passage once with its best score', async () => {
  const got = await gatherWindows(makeRetriever(), { queries: ['low', 'high'] });
  assert.equal(got.length, 1);
  assert.equal(got[0].score, 0.9);
});

test('plan failure falls back to basic needs; order preserved; errors isolated', async () => {
  const analysis = { claim: 'c', ...ANALYSIS };
  const w = win();
  const fetchImpl = async (_url, init) => {
    const body = JSON.parse(init.body);
    const system = body.messages[0].content, user = body.messages[1].content;
    if (system === 'P') return content('not json');                       // the plan never works
    if (user.includes('PROPOSITION: h1')) throw new TypeError('Failed to fetch');    // h1 call dies
    await new Promise((r) => setTimeout(r, user.includes('PROPOSITION: c') ? 30 : 0));   // the claim finishes last
    return content({ findings: [{ statement: 's', quote: 'Gamma delta.', passage_id: windowId(w), stance: 'supports' }] });
  };
  const order = [];
  const result = await runEvidence(OPENAI_CFG, analysis, makeRetriever(), prompts, { 'doc.pdf': { label: 'Doc', url: 'https://x.org/doc.pdf' } },
    { fetchImpl, onEntry: (e, done, total) => order.push([e.query, done, total]) });

  assert.deepEqual(result.evidence.map((e) => e.about), ['claim', 'ambiguity', 'assumption', 'assumption']);
  assert.deepEqual(order.map((o) => o[0]), ['c', 'always: a; b', 'h1', 'h2']);        // plan order, even though the claim was slowest
  assert.ok(order.every((o) => o[2] === 4));
  assert.match(result.plan_error, /^Could not plan the evidence search, used basic queries/);
  assert.ok(result.evidence[2].error);                                                // h1 failed, the run went on
  assert.ok(result.evidence[3].findings.length);                                      // h2 fine
  const f = result.evidence[0].findings[0];
  assert.deepEqual([f.pages, f.stance, f.label, f.url], [[1], 'supports', 'Doc', 'https://x.org/doc.pdf#page=1']);
  assert.deepEqual(result.index_documents, { 'doc.pdf': 'abc' });
});

test('a good plan is used and sent the available documents', async () => {
  const analysis = { claim: 'c', ...ANALYSIS };
  const seen = [];
  const fetchImpl = async (_url, init) => {
    const [sys, usr] = JSON.parse(init.body).messages.map((m) => m.content);
    seen.push([sys, usr]);
    if (sys === 'P') return content({ needs: [{ origin: 'claim', proposition: 'Prop', supporting: 'sup', refuting: 'ref', queries: ['q'] }] });
    return content({ findings: [] });
  };
  const result = await runEvidence(OPENAI_CFG, analysis, makeRetriever(), prompts, {}, { fetchImpl });
  const plan = JSON.parse(seen[0][1]);
  assert.deepEqual(plan.available_documents, ['doc.pdf']);
  assert.equal(plan.analysis.claim, 'c');
  assert.equal(result.plan_error, null);
  assert.deepEqual(result.plan.map((n) => n.id), ['N1']);
  assert.match(seen[1][1], /^PROPOSITION: Prop\nA SOURCE SUPPORTING IT WOULD SAY: sup\nA SOURCE REFUTING IT WOULD SAY: ref/);
});

test('analyze adds the claim and retries invalid structure', async () => {
  const answers = [content({ claim_type: 'x' }), content(ANALYSIS)];
  const a = await analyze(OPENAI_CFG, 'The climate has always changed', prompts, { fetchImpl: async () => answers.shift() });
  assert.equal(a.claim, 'The climate has always changed');
  assert.equal(answers.length, 0);
});
