import numpy as np

from climate_claims.indexing.store import Store
from climate_claims.retrieval.retriever import Retriever

N = 20


class FakeEmbedder:
    def __init__(self, vec):
        self.vec = vec / np.linalg.norm(vec)

    def encode_query(self, _q):
        return self.vec.astype(np.float32)


def make_store(tmp_path):
    store = Store(tmp_path)
    store.insert_sentences("d.pdf", [(i, 1, f"Sentence number {i} is here.", 1) for i in range(N)])
    todo = store.embeddable("d.pdf")
    store.save_vectors(np.array([i for i, _ in todo], dtype=np.int64), np.eye(N, dtype=np.float32))
    store.mark_done("d.pdf", "x")
    return store


def onehot(*idxs):
    v = np.zeros(N)
    for i in idxs:
        v[i] = 1
    return v


def test_window_is_hit_plus_context(tmp_path):
    r = Retriever(make_store(tmp_path), FakeEmbedder(onehot(10)))
    (w,) = r.search("q", k=1, context=7)
    assert (w.lo, w.hi) == (3, 17) and len(w.sentences) == 15
    assert w.hit_sentences == ["Sentence number 10 is here."]


def test_overlapping_windows_are_merged(tmp_path):
    r = Retriever(make_store(tmp_path), FakeEmbedder(onehot(5, 9)))
    (w,) = r.search("q", k=2, context=7)
    assert (w.lo, w.hi) == (0, 16)


def test_window_clipped_at_document_start(tmp_path):
    r = Retriever(make_store(tmp_path), FakeEmbedder(onehot(0)))
    (w,) = r.search("q", k=1, context=7)
    assert (w.lo, w.hi) == (0, 7) and len(w.sentences) == 8