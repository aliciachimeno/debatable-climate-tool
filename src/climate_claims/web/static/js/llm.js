import { complete, LLMError } from './providers.js';

export class ModelOutputError extends Error {
  constructor(message) { super(message); this.name = 'ModelOutputError'; }
}

export function parseJson(text) {
  text = text.replace(/<think>[\s\S]*?<\/think>/g, '');          // reasoning models
  const start = text.indexOf('{'), end = text.lastIndexOf('}');
  if (start < 0 || end < start) {
    throw new ModelOutputError(`No JSON object in model output: ${JSON.stringify(text.slice(0, 200))}`);
  }
  try { return JSON.parse(text.slice(start, end + 1)); }
  catch (e) { throw new ModelOutputError(`Invalid JSON in model output: ${e.message}`); }
}

/** Call the model and return parsed (and optionally validated) JSON; retry on bad output or network errors. */
export async function chatJson(cfg, system, user,
                               { temperature = 0.2, retries = 2, validate, signal, fetchImpl } = {}) {
  for (let attempt = 0; ; attempt++) {
    try {
      const data = parseJson(await complete(cfg, system, user, temperature, { signal, fetchImpl }));
      return validate ? validate(data) : data;
    } catch (e) {
      const retryable = e instanceof ModelOutputError || (e instanceof LLMError && e.status === 0);
      if (!retryable || attempt >= retries) throw e;
    }
  }
}
