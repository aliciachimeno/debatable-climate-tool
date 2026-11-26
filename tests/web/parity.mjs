// Usage: node parity.mjs <data dir> <json file with queries: [[name, [vector...]], ...]>
// Prints the windows the browser Retriever finds, for comparison with the Python Retriever.
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { loadIndexData, Retriever } from '../../src/climate_claims/web/static/js/retriever.js';

const [dataDir, queriesFile] = process.argv.slice(2);
const fetchImpl = async (url) => {
  const buf = await readFile(join(dataDir, url));
  return { ok: true, status: 200, json: async () => JSON.parse(buf.toString('utf8')),
           arrayBuffer: async () => buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) };
};
const queries = JSON.parse(await readFile(queriesFile, 'utf8'));
const vectors = new Map(queries.map(([q, v]) => [q, Float32Array.from(v)]));
const r = new Retriever(await loadIndexData('', fetchImpl), async (q) => vectors.get(q));
const out = {};
for (const [q] of queries) {
  out[q] = (await r.search(q, undefined, undefined)).map((w) =>
    ({ doc: w.doc, lo: w.lo, hi: w.hi, hits: w.hitSentences, sentences: w.sentences }));
}
console.log(JSON.stringify(out));
