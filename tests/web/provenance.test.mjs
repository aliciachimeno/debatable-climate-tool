import test from 'node:test';
import assert from 'node:assert/strict';
import { forSpan } from '../../src/climate_claims/web/static/js/provenance.js';

const DOC = 'ch2.pdf';
const prov = {
  docs: {
    [DOC]: {
      references: [
        { id: 'r0', raw: 'Kent, E.C., 2021: Study. Nature, 1, 2, doi:10.1/x.', title: 'Study.', page: 9, doi: '10.1/x' },
        { id: 'r1', raw: 'Kent, E.C., 2021b: Other.', title: 'Other.', page: 9 },
      ],
      sections: { '2.1': { title: 'Intro', lo: 0, hi: 5, page: 2 } },
      captions: { 'Figure 2.1': { title: 'Temp.', idx: 3, page: 4, data_url: 'https://d/1' } },
      figure_index: 'https://ipcc/figures',
    },
  },
  edges: {
    [DOC]: {
      1: [
        { k: 'paper', l: 'Kent, 2021', s: 'resolved', c: 1, r: 'r0' },
        { k: 'paper', l: 'Kent et al., 2021', s: 'ambiguous', c: 0.5, r: ['r0', 'r1'] },
        { k: 'section', l: 'Section 2.1', s: 'resolved', d: DOC, n: '2.1' },
        { k: 'figure', l: 'Figure 2.1', s: 'resolved', d: DOC, n: 'Figure 2.1' },
      ],
      2: [{ k: 'paper', l: 'Kent, 2021', s: 'resolved', c: 1, r: 'r0' }, { k: 'assessment', l: 'IPCC, 2013', s: 'not_found', c: 0 }],
    },
  },
};
const sources = { [DOC]: { url: 'https://x/ch2.pdf' } };

test('forSpan joins papers, sections and figures, each once', () => {
  const out = forSpan(prov, sources, DOC, 1, 2);
  assert.deepEqual(out.papers.map((p) => [p.label, p.type, p.status]),
    [['Kent, 2021', 'study', 'resolved'], ['Kent et al., 2021', 'study', 'ambiguous'], ['IPCC, 2013', 'assessment', 'not_found']]);
  assert.equal(out.papers[0].reference.doi_url, 'https://doi.org/10.1/x');
  assert.equal(out.papers[0].reference.url, 'https://x/ch2.pdf#page=9');
  assert.equal(out.papers[1].candidates.length, 2);
  assert.deepEqual(out.sections, [{ label: 'Section 2.1', status: 'resolved', document: DOC, page: 2,
    url: 'https://x/ch2.pdf#page=2', range: [0, 5], title: 'Intro' }]);
  assert.deepEqual(out.figures[0], { label: 'Figure 2.1', kind: 'figure', status: 'resolved', document: DOC, page: 4,
    title: 'Temp.', url: 'https://x/ch2.pdf#page=4', data_url: 'https://d/1', index_url: 'https://ipcc/figures' });
});

test('forSpan is null when nothing is cited, or there is no provenance', () => {
  assert.equal(forSpan(prov, sources, DOC, 7, 8), null);
  assert.equal(forSpan(null, sources, DOC, 1, 2), null);
  assert.equal(forSpan(prov, {}, DOC, 1, 1).sections[0].url, '');   // no source url: empty, like Python
});
