// Backend used on GitHub Pages: everything runs in the browser. The language model is called
// straight from here with the visitor's own key; the evidence index is a set of static files.

import { analyze, runEvidence } from './pipeline.js';
import { loadIndexData, Retriever } from './retriever.js';
import { loadBrowserEmbedder } from './embedder.js';

export function createBrowserBackend({ getConfig, dataUrl = 'data/', fetchImpl, loadEmbedder = loadBrowserEmbedder }) {
  const f = fetchImpl ?? ((...a) => fetch(...a));
  let promptsP = null, retrieverP = null, sourcesP = null, provenanceP = null;
  let onStatus = () => {};

  const text = async (name) => {
    const r = await f(`${dataUrl}${name}`);
    if (!r.ok) throw new Error(`Could not load ${name} (HTTP ${r.status}).`);
    return r.text();
  };
  const retry = (make, reset) => make().catch((e) => { reset(); throw e; });   // a failed load is tried again next time

  const prompts = () => (promptsP ??= retry(async () => {
    const names = ['analyze', 'plan', 'evidence'];
    const texts = await Promise.all(names.map((n) => text(`prompts/${n}.md`)));
    return Object.fromEntries(names.map((n, i) => [n, texts[i]]));
  }, () => { promptsP = null; }));

  const sources = () => (sourcesP ??= retry(async () => JSON.parse(await text('sources.json')),
                                            () => { sourcesP = null; }));

  // optional: without provenance.json the findings simply have no evidence chain
  const provenance = () => (provenanceP ??= (async () => {
    try { return JSON.parse(await text('provenance.json')); } catch { return null; }
  })());

  const retriever = () => (retrieverP ??= retry(async () => {
    onStatus('Loading the evidence index…');
    const data = await loadIndexData(dataUrl, f);
    const embed = await loadEmbedder(data.meta, (m) => onStatus(m));
    return new Retriever(data, embed);
  }, () => { retrieverP = null; }));

  return {
    name: 'browser',
    needsSettings: true,
    notice: '',
    /** Start downloading the index and the search model while the model reads the claim. */
    prepare(status = () => {}) { onStatus = status; retriever().catch(() => {}); },

    async analyze(claim, { signal } = {}) {
      return analyze(getConfig(), claim, await prompts(), { signal, fetchImpl });
    },

    async evidence(analysis, { signal, onUpdate }) {
      const cfg = getConfig();
      const shown = [];
      onStatus = (status) => onUpdate({ entries: [], done: 0, total: 0, running: true, status });
      const [r, p, s, prov] = await Promise.all([retriever(), prompts(), sources(), provenance()]);
      onUpdate({ entries: [], done: 0, total: 0, running: true, status: 'Planning the evidence search…' });
      const result = await runEvidence(cfg, analysis, r, p, s, {
        signal, fetchImpl, provenance: prov,
        onEntry: (entry, done, total) => { shown.push(entry); onUpdate({ entries: [...shown], done, total, running: true }); },
      });
      onUpdate({ entries: result.evidence, done: result.evidence.length, total: result.evidence.length,
                 running: false, notice: result.plan_error });
      return result;
    },
  };
}
