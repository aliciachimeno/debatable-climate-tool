"""Build the static site (docs/) for GitHub Pages from the local index.

The site has no backend: the browser loads these files, embeds the query itself and searches
here, then calls the visitor's language model directly. `docs/` is generated (run this again
after changing the front-end or the index); do not edit it by hand.

  docs/index.html, docs/static/   the interface (copied from src/climate_claims/web/static)
  docs/data/meta.json             embedding model, dimensions, retrieval settings, document list
  docs/data/sentences.json        {"docs": [{"pages": [...], "texts": [...]}]}  every sentence, in reading order
  docs/data/vec_map.json          flat [docIdx, sentenceIdx, ...]  which sentence each vector belongs to
  docs/data/vectors.i8            int8 matrix (count x dim): vector * 127, rows are unit length
  docs/data/sources.json          document labels and links (data/raw/sources.json)
  docs/data/provenance.json       what each sentence cites: papers, sections, figures (claims provenance)
  docs/data/prompts/              the same prompt files the command-line tool uses
"""
import json
import shutil
from pathlib import Path

import numpy as np

from .config import settings
from .embedding import QUERY_PREFIX
from .indexing.store import Store
from .llm import PROMPTS_DIR

QUANT_SCALE = 127
PROMPTS = ("analyze", "plan", "evidence")
STATIC = Path(__file__).parent / "web" / "static"


def quantize(vecs: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(vecs * QUANT_SCALE), -QUANT_SCALE, QUANT_SCALE).astype(np.int8)


def _dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def export_web(out_dir: Path | None = None, store: Store | None = None) -> Path:
    site = Path(out_dir or settings.web_dir)
    out = site / "data"
    store = store or Store()
    ids, vecs = store.load_vectors()
    if vecs is None or len(ids) == 0:
        raise SystemExit("The index is empty. Run: claims index")

    hashes = store.doc_hashes()
    names = sorted(hashes)
    doc_no = {n: i for i, n in enumerate(names)}

    pages = {n: [] for n in names}
    texts = {n: [] for n in names}
    where = {}                                   # sentence id -> (doc number, idx in doc)
    for sid, doc, idx, page, text in store.db.execute(
            "SELECT id, doc, idx, page, text FROM sentences ORDER BY doc, idx"):
        if idx != len(texts[doc]):
            raise SystemExit(f"{doc}: sentence indexes are not contiguous; run claims index --rebuild")
        pages[doc].append(page)
        texts[doc].append(text)
        where[sid] = (doc_no[doc], idx)

    sources = {}
    if Path(settings.sources_file).exists():
        sources = json.loads(Path(settings.sources_file).read_text(encoding="utf-8"))

    out.mkdir(parents=True, exist_ok=True)
    _dump(out / "sentences.json", {"docs": [{"pages": pages[n], "texts": texts[n]} for n in names]})
    _dump(out / "vec_map.json", [n for sid in ids.tolist() for n in where[sid]])
    quantize(vecs).tofile(out / "vectors.i8")
    _dump(out / "sources.json", sources)
    if Path(settings.provenance_file).exists():       # optional: the evidence chain of each finding
        shutil.copyfile(settings.provenance_file, out / "provenance.json")
    _dump(out / "meta.json", {
        "emb_model": settings.emb_model,
        "query_prefix": QUERY_PREFIX,
        "dim": int(vecs.shape[1]),
        "count": int(vecs.shape[0]),
        "quant_scale": QUANT_SCALE,
        "context": settings.context,
        "top_k": settings.top_k,
        "docs": [{"name": n, "sha": hashes[n][:12], "title": sources.get(n, {}).get("label", n)} for n in names],
    })

    (out / "prompts").mkdir(exist_ok=True)
    for name in PROMPTS:
        shutil.copyfile(PROMPTS_DIR / f"{name}.md", out / "prompts" / f"{name}.md")

    # the interface itself: index.html at the root, everything else under static/
    shutil.copyfile(STATIC / "index.html", site / "index.html")
    shutil.rmtree(site / "static", ignore_errors=True)
    shutil.copytree(STATIC, site / "static", ignore=shutil.ignore_patterns("index.html", "__pycache__"))
    (site / ".nojekyll").touch()
    return site
