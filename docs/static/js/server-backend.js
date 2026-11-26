// Backend used when the page is served by `claims serve`: the Python app does the work and the
// language model is configured there (environment variables), so the page has no settings box.

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(path, body, signal) {
  const res = await fetch(path, body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal,
  } : { signal });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

export async function detectServer() {
  try {
    const res = await fetch('api/health');
    const data = res.ok ? await res.json() : null;
    return data?.ok ? data : null;
  } catch { return null; }
}

export function createServerBackend(health) {
  return {
    name: 'server',
    needsSettings: false,
    notice: health.index_ready ? '' :
      `The document index is not ready: ${health.message || 'run `claims index`'} You can still analyse claims, but the evidence tab will be empty.`,
    prepare() {},
    analyze: (claim, { signal } = {}) => api('api/analyze', { claim }, signal),

    /** Starts the evidence job and polls it; calls onUpdate with the entries found so far. */
    async evidence(analysis, { signal, onUpdate }) {
      const { job } = await api('api/evidence', { analysis }, signal);
      for (;;) {
        const j = await api(`api/evidence/${job}`, null, signal);
        const running = j.status === 'running';
        if (j.status === 'error') throw new Error(j.error);
        onUpdate({
          entries: j.status === 'done' ? j.result.evidence : j.entries, done: j.done, total: j.total, running,
          notice: j.status === 'done' ? j.result.plan_error : null,
        });
        if (!running) return j.result;
        await sleep(1500);
        if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
      }
    },
  };
}
