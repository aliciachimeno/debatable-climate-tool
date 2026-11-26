# Climate Claims

Type a claim about climate change, such as *"The climate has always changed"*. The tool breaks the claim down and looks for evidence in the IPCC reports.

## What it does

```
Claim → 1. Analysis → 2. Evidence plan → 3. Evidence → 4. Evaluation → 5. Report
```

| Step | What happens | Status |
|---|---|---|
| 1. Analysis | Works out what the claim literally says, what it implies, what is ambiguous, and what it assumes | ✅ Done |
| 2. Evidence plan | Lists the scientific questions to ask, and what results would support or refute the claim | ✅ Done |
| 3. Evidence | Finds matching passages in the IPCC AR6 WG1 reports and keeps only verified quotes | ✅ Done |
| 4. Evaluation | Says what we can and cannot conclude | 🕓 Planned |
| 5. Final report | Puts everything together in one readable output | 🕓 Planned |

## Quick start

You need Python 3.11 or newer.

```bash
# 1. Install
uv sync                      # or: pip install -e .

# 2. Configure (create a .env file; never commit it)
OPENWEBUI_URL=https://your-openwebui-server
OPENWEBUI_API_KEY=your-key
OPENWEBUI_MODEL=your-model-name

# 3. Add the IPCC PDFs to data/raw/01_assessments/ipcc_ar6_wg1/, then build the index
claims index

# 4. Analyse a claim
claims run "The climate has always changed"
```

Results are saved in `runs/<date>_<claim>/`:

- `analysis.json`: what the claim means and assumes
- `plan.json`: the questions to answer (you can edit it by hand)
- `evidence.json`: the quotes found, each marked as supports, refutes or context

## All commands

| Command | What it does |
|---|---|
| `claims index` | Builds the search index (`--rebuild` starts over) |
| `claims check-index` | Checks the index is consistent |
| `claims analyze "<claim>"` | Step 1 only |
| `claims plan runs/<run>/analysis.json` | Step 2 only |
| `claims evidence runs/<run>/analysis.json` | Step 3 only |
| `claims run "<claim>"` | Steps 1 to 3 in one go |
| `pytest` | Runs the tests (no internet or API key needed) |

## How it works

1. **Index.** PDFs are split into sentences, and each sentence is turned into an embedding so it can be searched by meaning.
2. **Analysis.** An LLM reads the claim and returns structured JSON. It gives the claim type (descriptive, causal, predictive or policy), the implied argument, the ambiguities and the hidden assumptions. It also flags mismatches, for example a descriptive premise used to support a causal conclusion.
3. **Evidence plan.** An LLM turns the analysis into 4 to 8 questions. Each one says what result would support or refute the claim, and includes search queries.
4. **Evidence.** For each question, the tool retrieves the best-matching passages. The LLM extracts findings from them. A finding is kept only if its quote appears word for word in the source, so invented quotes are dropped. Page numbers come from the index, not from the LLM.

## Known limits

- Evidence comes only from the IPCC AR6 WG1 PDFs. No other papers are searched yet.
- Whether a finding supports or refutes the claim is the LLM's judgement. It is not checked automatically.
- Verification checks that a quote exists, not that it answers the question.
- Search is by meaning only. There is no keyword matching or reranking.
- Review `analysis.json` and `plan.json` by hand. Their quality is not evaluated automatically.
- Sources named in the plan (`suggested_sources`) come from the model's memory and are not verified.

## Project layout

```
src/climate_claims/
  cli.py          commands
  config.py       settings
  llm.py          Open WebUI client
  schemas.py      data structures
  analysis/       step 1
  evidence/       steps 2 and 3
  indexing/       PDF loading and index building
  retrieval/      search
  prompts/        the LLM prompts (editable)
tests/            automated tests
data/raw/         source PDFs and catalog
```

## Roadmap

- [ ] Critical evaluation: what can and cannot be concluded
- [ ] Final report output
- [ ] Database of contested claims, and a test run over them
- [ ] Search beyond IPCC (academic literature)
- [ ] Automatic check that findings answer the question