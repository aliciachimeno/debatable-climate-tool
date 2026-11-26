# Climate Claims

Type a claim about climate change (e.g. *"The climate has always changed"*). The tool:

1. **Analyses the claim**: what it says literally, what it implies, what is ambiguous,
   what it takes for granted, and whether its premise supports its conclusion.
2. **Finds evidence** in the IPCC AR6 documents as word-for-word quotes with the PDF page.
   A quote is kept only if it really appears in the passage it cites.

It runs as a **web page** (GitHub Pages, no backend) and as a **command-line tool**.
Both use the same prompts and the same verification.

## Web page

Open https://aliciachimeno.github.io/debatable-climate-tool/ and fill in
*Connect a language model*:

| Provider | Base URL | Model |
|---|---|---|
| OpenAI | preset | a model id from your account |
| Anthropic (Claude) | preset | a Claude model id |
| OpenRouter | preset | `provider/model-name` |
| Other OpenAI-compatible (Open WebUI, Ollama, vLLM, LM Studio) | everything before `/chat/completions` | the server's model name |

Use **Test connection** before running a claim.

- There is no backend. The browser calls your provider directly, so your key never
  touches this project's servers. It is kept in session storage (forgotten when the tab
  closes) unless you tick *Remember my key on this device*.
- The provider must allow cross-origin (CORS) requests. A server on a private network
  is only reachable from machines that can reach it.
- Search runs in the browser: the first visit downloads the index (~5 MB) and the
  embedding model (~35 MB, cached afterwards).

## Run locally

```bash
python -m http.server -d docs 8000      # then open http://localhost:8000
```

## Command line (Python >= 3.11)

```bash
uv sync                      # or: pip install -e .
cp .env.example .env         # fill in provider, base URL, key, model
claims index                 # build data/index from data/raw (--rebuild to start over)
claims check-index           # verify the index
claims run "The climate has always changed"   # analysis + evidence -> runs/<date>_<claim>/
claims export-web            # regenerate docs/data for the web page
```

Other commands: `claims analyze "<claim>"` (stage 1) and
`claims evidence runs/<run>/analysis.json` (stage 2).

## Updating the web data

After changing documents or index settings:

```bash
claims index && claims export-web
git add docs && git commit -m "Update web data" && git push
```

Pages: Settings -> Pages -> Deploy from a branch -> `main` / `/docs`.

## Tests

```bash
PYTHONPATH=src pytest
node --test tests/web/*.test.mjs
```

## Limits

- Evidence comes only from the IPCC AR6 documents in `data/raw/`.
- Quotes are checked to exist in the cited passage, not to answer the question.
  Whether a finding supports or undermines a claim is the model's judgement.
- Retrieval is purely semantic (sentence embeddings), with no keyword search or reranking.