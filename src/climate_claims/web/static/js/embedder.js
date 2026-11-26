// Embeds the search query in the browser with the same model used to build the index
// (bge-small-en-v1.5, CLS pooling, normalised), via transformers.js. Downloads ~35 MB once; the
// browser caches it afterwards.

const TRANSFORMERS_URL = 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@3';

// The index records the Python model name; transformers.js needs the ONNX copy of it.
export const browserModelName = (name) => name.replace(/^BAAI\//, 'Xenova/');

export async function loadBrowserEmbedder(meta, onStatus = () => {}) {
  onStatus('Loading the search model (about 35 MB, first visit only)…');
  const { pipeline } = await import(TRANSFORMERS_URL);
  const extractor = await pipeline('feature-extraction', browserModelName(meta.emb_model), {
    progress_callback: (p) => {
      if (p.status === 'progress' && Number.isFinite(p.progress)) {
        onStatus(`Loading the search model… ${Math.round(p.progress)}%`);
      }
    },
  });
  return async (query) => {
    const out = await extractor(meta.query_prefix + query, { pooling: 'cls', normalize: true });
    return Float32Array.from(out.data);
  };
}
