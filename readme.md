# Debatable climate change tool

Analyse a claim about climate change and find verified evidence for it in IPCC AR6 WG1 documents.

Claim → conceptual analysis → evidence from indexed documents → (planned) critical evaluation → (planned) final output.

## Setup

Requires Python >= 3.11.

```bash
uv sync                      # or: pip install -e .
```

Configuration is read from the environment (or a `.env` file; see `.env.example`). It is only used by the command line and by `claims serve`: the GitHub Pages site asks for the same values in its *Language model* box instead.

| Variable | Meaning |
|---|---|
| `LLM_PROVIDER` | `openai` (any OpenAI-compatible server: OpenAI, OpenRouter, Open WebUI, Ollama, vLLM, LM Studio...; the default) or `anthropic` (Claude API) |
| `LLM_BASE_URL` | everything before `/chat/completions`, e.g. `https://api.openai.com/v1` or `https://your-server/api` for Open WebUI. Not needed for `anthropic` |
| `LLM_API_KEY` | your key (optional for a server on localhost). Never commit it |
| `LLM_MODEL` | model name |
| `LLM_TIMEOUT` | request timeout in seconds (default 600) |
| `LLM_WORKERS` | parallel model calls in the evidence step (default 4) |

The old `OPENWEBUI_URL`, `OPENWEBUI_API_KEY` and `OPENWEBUI_MODEL` still work.

Other settings (embedding model, context size, top-k, paths) live in `src/climate_claims/config.py`.

## Usage

Put the PDFs in `data/raw/01_assessments/ipcc_ar6_wg1/`, then:

```bash
claims index                 # build the index (incremental; --rebuild to start over)
claims check-index           # verify the index is consistent
claims analyze "The climate has always changed"   # stage 1 only -> analysis.json
claims evidence runs/<run>/analysis.json          # stage 2 for a saved analysis
claims run "The climate has always changed"       # stages 1 + 2 in one go
claims serve                 # the web interface on http://127.0.0.1:8000 (model settings from the environment)
claims export-web            # build the static site (docs/) for GitHub Pages
pytest                       # tests need no network or API key
node --test tests/web/*.test.mjs   # the browser code
```

Each `analyze` / `run` writes to `runs/<YYYY-MM-DD>_<claim-slug>/`:
`analysis.json` and `evidence.json`.

## How it works

**Indexing** (`indexing/`)
- PDFs are read page by page and split into sentences (`pysbd`).
- Sentences with at least `min_words` (8) words are embedded with `BAAI/bge-small-en-v1.5`; shorter ones are stored only as context.
- Sentences go to SQLite (`sentences.db`), vectors to `vectors.npy` / `ids.npy`.
- Writes are crash-safe: vectors are saved atomically first, the DB commit comes after, and orphaned vectors are dropped on load.
- Each document's SHA-256 is stored; if a file changes after indexing, `claims index --rebuild` is required.

**Stage 1: analysis** (`analysis/analyze.py`, `prompts/analyze.md`)
One LLM call returns structured JSON (`schemas.Analysis`):
claim type (`descriptive_factual`, `causal_attribution`, `predictive`, `policy_value`), literal meaning, implied argument, ambiguities, hidden assumptions, and a premise/conclusion type-mismatch check (e.g. a descriptive premise used to support a causal conclusion).

**Stage 2: evidence** (`evidence/`)
1. Queries are built from the claim, each ambiguity, and each hidden assumption.
2. Each query retrieves the top `top_k` (6) sentences by cosine similarity, expanded to ±`context` (7) sentences; overlapping windows in the same document are merged.
3. The LLM extracts findings (statement + verbatim quote + passage id) from those passages only.
4. `verify.py` keeps a finding only if its quote appears literally (case and whitespace insensitive) in the cited window. Page numbers come from the index, never from the LLM.

Findings that fail verification are discarded silently. An evidence entry with `error` means the model never returned valid JSON for that query.

## The web page on GitHub Pages

The page is static: there is no server, so it runs the whole pipeline in the visitor's browser. The evidence index is shipped as files (about 5 MB), the claim is embedded with the same small model (downloaded once, about 35 MB), and the language model is called **directly from the browser with the visitor's own key**. The key never touches this project: it stays in the browser's session storage (or local storage if the visitor ticks *Remember my key*).

The *Language model* box at the top right unfolds to set provider, base URL, API key and model (OpenAI, Anthropic/Claude, OpenRouter, or any OpenAI-compatible server) and has a *Test connection* button. Because calls come from the browser, the provider must allow cross-origin (CORS) requests; OpenAI, Anthropic and OpenRouter do. A self-hosted or internal server may not, and an `https://` page cannot call a plain `http://` server except `http://localhost`.

Publishing (the index is built once, anywhere, for example on a cluster node; the model is never needed for this step):

```bash
claims index          # build data/index (needs the PDFs in data/raw/...)
claims export-web     # writes docs/ : the interface (copied from src/climate_claims/web/static) and docs/data
git add docs && git commit -m "Update site" && git push
```

Then, once: **Settings → Pages → Deploy from a branch → `main` / `/docs`**. To try it locally: `python -m http.server -d docs`.

`docs/` is generated: edit the interface in `src/climate_claims/web/static/` and run `claims export-web` again. The same files are served by `claims serve`, which uses the Python pipeline instead of the in-browser one.

## Known limits

- Evidence comes only from the indexed IPCC AR6 WG1 PDFs; no other literature.
- Retrieval is purely semantic (sentence embeddings); there is no keyword or reranking step.
- Verification checks that quotes exist, not that they actually answer the question. `prompts/judge.md` exists for that purpose but is not wired into the pipeline yet.
- Quality of the analysis (stage 1) is not evaluated automatically; review outputs by hand.
- `data/raw/catalog.txt` still has `[fill in]` placeholders for key claims per document.

## Layout

```
src/climate_claims/
  cli.py            commands: index, check-index, analyze, evidence, run
  config.py         settings (env + defaults)
  llm.py            Open WebUI chat client, JSON parsing and retries
  schemas.py        Analysis, Window, Finding dataclasses
  analysis/         stage 1
  evidence/         stage 2 (pipeline.py, verify.py)
  indexing/         loaders, sentence splitting, store, build, check
  retrieval/        Retriever (embedding search + context windows)
  prompts/          analyze.md, evidence.md, judge.md
tests/              test_verify.py, test_retriever.py
data/raw/           source PDFs and catalog.txt
```