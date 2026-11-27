# Climate Claims

Type a claim about climate change (e.g. *"The climate has always changed"*). The tool:

1. **Analyses the claim**: what it says literally, what it implies, what is ambiguous,
   what it takes for granted, and whether its premise supports its conclusion.
2. **Finds evidence** in the IPCC AR6 documents as word-for-word quotes with the PDF page.
   A quote is kept only if it really appears in the passage it cites.
3. **Traces each quote** to what it cites: the papers (with DOI), chapter sections and
   figures behind it, shown as an *evidence chain* under the quote.

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
claims provenance            # link every sentence to its cited papers, sections, figures
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

## Evidence chain

The IPCC reports summarise other research, so a quote usually points elsewhere: to papers
`(Freeman et al., 2017)`, to chapter sections `{2.3.1.1}`, to figures `Figure 2.11`. `claims provenance`
reads those pointers from the indexed sentences and resolves them. It runs offline, after
`claims index`, with no language model, and writes `data/index/provenance.json`
(`claims export-web` copies it to `docs/data`; without the file, findings simply show no chain).

```
quote -> chapter section  (sections, with the pages they span)
      -> cited paper      (the chapter's reference list entry, with its DOI)
      -> figure / table / box  (caption, page, link to the IPCC figure index)
```

How it works (`src/climate_claims/provenance/`):

- `mentions.py` finds the pointers in a sentence (papers, `IPCC, 2013`, `Section 2.3`, `{...}`
  pointers, figures, tables, boxes, FAQs, including lists such as "Figures 2.26 and 3.26").
- `references.py` rebuilds a chapter's reference list from its sentences and matches citations by
  first author + year. "et al." (3 or more authors) and "A and B" tell apart same-year entries.
- `structure.py` finds section ranges (checked against the table of contents) and captions.
- `resolve.py` turns each mention into a link with a **status**: `resolved`, `ambiguous`,
  `not_found`, `not_indexed` (the target is in a document that is not indexed, e.g. Chapter 4)
  or `no_reference_list`. Nothing is dropped, so `claims provenance` can report coverage.
- `chain.py` joins the links of a quote's sentences into the chain shown in the interface; the
  browser has the same join in `web/static/js/provenance.js` (a test keeps them equal).

On the Chapter 1-3 PDFs, 92-95% of in-text citations resolve to a reference entry (about 98%
of those entries have a DOI) and 93-96% of figure mentions to a caption.

Optional: `data/figure_links.json` adds a page, data or code link per figure:

```json
{"IPCC_AR6_WGI_Chapter02.pdf": {"Figure 2.11": {"url": "...", "data_url": "...", "code_url": "..."}}}
```

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
- The evidence chain links what the quote's own sentences cite. It does not read the cited papers,
  so it says which studies stand behind a quote, not what each study shows.
- Figure links go to the IPCC figure index (https://www.ipcc.ch/report/ar6/wg1/figures) and to the
  caption page in the PDF. Per-figure data links need `data/figure_links.json`.
- Corporate authors ("... Consortium, 2019") and references in documents that have no parsed
  reference list stay unresolved. Captions in the Synthesis Report SPM are not recognised.