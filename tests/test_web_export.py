import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from climate_claims.indexing.store import Store
from climate_claims.retrieval.retriever import Retriever
from climate_claims.web_export import export_web

N = 40
DIM = 16
PARITY = Path(__file__).parent / "web" / "parity.mjs"


def make_store(tmp_path):
    rng = np.random.default_rng(0)
    vecs = rng.normal(size=(2 * N, DIM)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    store = Store(tmp_path / "index")
    for d, name in enumerate(["a.pdf", "b.pdf"]):
        store.insert_sentences(name, [(i, 1 + i // 10, f"Sentence {i} of {name} says something.", 1)
                                      for i in range(N)])
        todo = store.embeddable(name)
        ids, v = store.load_vectors()
        new_ids = np.array([i for i, _ in todo], dtype=np.int64)
        new_v = vecs[d * N:(d + 1) * N]
        store.save_vectors(np.concatenate([ids, new_ids]), new_v if v is None else np.vstack([v, new_v]))
        store.mark_done(name, "f" * 64)
    return store, vecs


class FakeEmbedder:
    def __init__(self, table):
        self.table = table

    def encode_query(self, q):
        return self.table[q]


def test_export_files(tmp_path):
    store, _ = make_store(tmp_path)
    site = export_web(tmp_path / "site", store)
    out = site / "data"
    meta = json.loads((out / "meta.json").read_text())
    assert meta["count"] == 2 * N and meta["dim"] == DIM
    assert [d["name"] for d in meta["docs"]] == ["a.pdf", "b.pdf"]
    assert (out / "vectors.i8").stat().st_size == 2 * N * DIM
    assert len(json.loads((out / "vec_map.json").read_text())) == 2 * N * 2
    sents = json.loads((out / "sentences.json").read_text())
    assert len(sents["docs"]) == 2 and len(sents["docs"][0]["texts"]) == N
    for name in ("analyze", "plan", "evidence"):
        assert (out / "prompts" / f"{name}.md").exists()
    assert isinstance(json.loads((out / "sources.json").read_text()), dict)
    # the interface is copied next to the data, with relative asset paths (Pages serves it under /<repo>/)
    html = (site / "index.html").read_text(encoding="utf-8")
    assert 'href="static/app.css"' in html and 'src="static/app.js"' in html
    for name in ("app.js", "app.css", "js/pipeline.js", "js/providers.js", "js/browser-backend.js"):
        assert (site / "static" / name).exists()
    assert not (site / "static" / "index.html").exists()
    assert (site / ".nojekyll").exists()


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_browser_retriever_matches_python(tmp_path):
    store, vecs = make_store(tmp_path)
    out = export_web(tmp_path / "site", store) / "data"
    # queries are existing vectors, nudged: top hits are well separated, so int8 rounding cannot reorder them
    rng = np.random.default_rng(1)
    table = {}
    for name, rows in {"q1": [3], "q2": [3, 7, 55], "q3": [0, 39, 40, 79, 20]}.items():
        q = vecs[rows].sum(axis=0) + rng.normal(scale=0.01, size=DIM)
        table[name] = (q / np.linalg.norm(q)).astype(np.float32)

    queries = tmp_path / "queries.json"
    queries.write_text(json.dumps([[k, v.tolist()] for k, v in table.items()]))
    run = subprocess.run(["node", str(PARITY), str(out), str(queries)], capture_output=True, text=True, check=True)
    js = json.loads(run.stdout)

    py = Retriever(store, FakeEmbedder(table))
    for name in table:
        expected = [{"doc": w.doc, "lo": w.lo, "hi": w.hi, "hits": w.hit_sentences,
                     "sentences": [[p, t] for p, t in w.sentences]} for w in py.search(name)]
        got = js[name]
        key = lambda w: (w["doc"], w["lo"])
        assert sorted(got, key=key) == sorted(expected, key=key), name
