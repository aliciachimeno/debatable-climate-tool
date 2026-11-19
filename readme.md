# Climate Claims

Analyse a claim about climate change and find verified evidence for it in IPCC AR6 WG1 documents.

Claim → conceptual analysis → evidence from indexed documents → (planned) critical evaluation → (planned) final output.

## Setup

Requires Python >= 3.11.

```bash
uv sync                      # or: pip install -e .
```

Configuration is read from the environment (or a `.env` file):

| Variable | Meaning |
|---|---|
| `OPENWEBUI_URL` | Base URL of the Open WebUI server |
| `OPENWEBUI_API_KEY` | API key for that server (required, never commit it) |
| `OPENWEBUI_MODEL` | Model name served by Open WebUI (required) |
| `LLM_TIMEOUT` | Request timeout in seconds (default 600) |

Other settings (embedding model, context size, top-k, paths) live in `src/climate_claims/config.py`.

## Usage

Put the PDFs in `data/raw/01_assessments/ipcc_ar6_wg1/`, then:

```bash
claims index                 # build the index (incremental; --rebuild to start over)
claims check-index           # verify the index is consistent
claims analyze "The climate has always changed"   # stage 1 only -> analysis.json
claims evidence runs/<run>/analysis.json          # stage 2 for a saved analysis
claims run "The climate has always changed"       # stages 1 + 2 in one go
pytest                       # tests need no network or API key
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