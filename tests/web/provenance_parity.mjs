// Usage: node provenance_parity.mjs <provenance.json> <sources.json> <spans.json>
// Prints forSpan() for each [doc, lo, hi] so tests/test_provenance_parity.py can compare it with Python.
import { readFile } from 'node:fs/promises';
import { forSpan } from '../../src/climate_claims/web/static/js/provenance.js';

const [provFile, sourcesFile, spansFile] = process.argv.slice(2);
const read = async (f) => JSON.parse(await readFile(f, 'utf8'));
const [prov, sources, spans] = await Promise.all([read(provFile), read(sourcesFile), read(spansFile)]);
console.log(JSON.stringify(spans.map(([doc, lo, hi]) => forSpan(prov, sources, doc, lo, hi))));
