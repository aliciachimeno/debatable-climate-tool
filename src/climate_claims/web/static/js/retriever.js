// Port of src/climate_claims/retrieval/retriever.py, over the files made by `claims export-web`.

export async function loadIndexData(base = 'data/', fetchImpl = globalThis.fetch.bind(globalThis)) {
  const get = async (name, as) => {
    const r = await fetchImpl(base + name);
    if (!r.ok) throw new Error(`Could not load ${name} (HTTP ${r.status}). Run "claims export-web" and publish docs/data.`);
    return r[as]();
  };
  const [meta, sentences, vecMap, buf] = await Promise.all([
    get('meta.json', 'json'), get('sentences.json', 'json'), get('vec_map.json', 'json'),
    get('vectors.i8', 'arrayBuffer'),
  ]);
  return { meta, docs: sentences.docs, vecMap, vecs: new Int8Array(buf) };
}

export class Retriever {
  /** embed: async (query) => unit-length Float32Array(dim), same model as the index. */
  constructor({ meta, docs, vecMap, vecs }, embed) {
    if (vecs.length !== meta.count * meta.dim || vecMap.length !== meta.count * 2) {
      throw new Error('The exported index is incomplete or corrupt. Run "claims export-web" again.');
    }
    Object.assign(this, { meta, docs, vecMap, vecs, embed });
  }

  async search(query, k = this.meta.top_k, context = this.meta.context) {
    const q = await this.embed(query);
    const { dim, count, quant_scale: scale } = this.meta;
    if (q.length !== dim) throw new Error(`Query embedding has ${q.length} dimensions, the index has ${dim}.`);

    const scores = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      let s = 0;
      const o = i * dim;
      for (let j = 0; j < dim; j++) s += this.vecs[o + j] * q[j];
      scores[i] = s / scale;
    }
    const top = Array.from(scores.keys()).sort((a, b) => scores[b] - scores[a]).slice(0, k);

    const hits = top.map((i) => {
      const doc = this.vecMap[2 * i], idx = this.vecMap[2 * i + 1];
      return { doc, idx, score: scores[i], text: this.docs[doc].texts[idx] };
    }).sort((a, b) => a.doc - b.doc || a.idx - b.idx);

    const windows = [];
    for (const h of hits) {
      const lo = Math.max(0, h.idx - context), hi = h.idx + context;
      const last = windows[windows.length - 1];
      if (last && last.docNo === h.doc && lo <= last.hi + 1) {           // overlapping: merge
        last.hi = Math.max(last.hi, hi);
        last.score = Math.max(last.score, h.score);
        last.hitSentences.push(h.text);
      } else {
        windows.push({ docNo: h.doc, doc: this.meta.docs[h.doc].name, lo, hi, score: h.score, hitSentences: [h.text] });
      }
    }
    for (const w of windows) {
      const { pages, texts } = this.docs[w.docNo];
      w.sentences = [];
      for (let i = w.lo; i <= Math.min(w.hi, texts.length - 1); i++) w.sentences.push([pages[i], texts[i]]);
    }
    return windows.sort((a, b) => b.score - a.score);
  }
}
