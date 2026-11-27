// Port of src/climate_claims/provenance/chain.py: the evidence chain of a finding.
// Reads data/provenance.json (made by `claims provenance`, copied by `claims export-web`).
// tests/test_provenance_parity.py keeps this and the Python version equal.

const sourceUrl = (sources, doc, page) => {
  const url = sources?.[doc]?.url;
  return url ? `${url}#page=${page}` : '';
};

function reference(prov, sources, doc, id) {
  const r = prov.docs[doc].references.find((x) => x.id === id);
  const out = { id, text: r.raw, title: r.title, page: r.page, document: doc, url: sourceUrl(sources, doc, r.page) };
  if (r.doi) { out.doi = r.doi; out.doi_url = `https://doi.org/${r.doi}`; }
  return out;
}

function paper(prov, sources, doc, e) {
  const item = { label: e.l, type: e.k === 'assessment' ? 'assessment' : 'study', status: e.s };
  if ('c' in e) item.confidence = e.c;
  if (e.s === 'resolved') item.reference = reference(prov, sources, doc, e.r);
  else if (e.s === 'ambiguous') item.candidates = e.r.slice(0, 4).map((id) => reference(prov, sources, doc, id));
  return item;
}

function section(prov, sources, e) {
  const item = { label: e.l, status: e.s };
  if (e.s === 'resolved') {
    const s = prov.docs[e.d].sections[e.n];
    Object.assign(item, { document: e.d, page: s.page, url: sourceUrl(sources, e.d, s.page), range: [s.lo, s.hi] });
    if (s.title) item.title = s.title;
  }
  return item;
}

function figure(prov, sources, e) {
  const item = { label: e.l, kind: e.k, status: e.s };
  if (e.s === 'resolved') {
    const c = prov.docs[e.d].captions[e.n];
    Object.assign(item, { document: e.d, page: c.page, title: c.title, url: sourceUrl(sources, e.d, c.page) });
    for (const key of ['data_url', 'code_url']) if (c[key]) item[key] = c[key];
    if (c.url) item.figure_url = c.url;
    const index = prov.docs[e.d].figure_index;
    if (index) item.index_url = index;
  }
  return item;
}

/** Everything the sentences lo..hi of `doc` point to, each item once, in reading order; null if nothing. */
export function forSpan(prov, sources, doc, lo, hi) {
  if (!prov?.edges) return null;
  const edges = prov.edges[doc] ?? {};
  const seen = new Set();
  const out = { papers: [], sections: [], figures: [] };
  for (let idx = lo; idx <= hi; idx++) {
    for (const e of edges[String(idx)] ?? []) {
      const key = `${e.k}\u0000${e.l}`;
      if (seen.has(key)) continue;
      seen.add(key);
      if (e.k === 'paper' || e.k === 'assessment') out.papers.push(paper(prov, sources, doc, e));
      else if (e.k === 'section') out.sections.push(section(prov, sources, e));
      else out.figures.push(figure(prov, sources, e));
    }
  }
  return out.papers.length || out.sections.length || out.figures.length ? out : null;
}
