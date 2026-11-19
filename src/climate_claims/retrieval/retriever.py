import numpy as np

from ..config import settings
from ..embedding import Embedder
from ..indexing.store import Store
from ..schemas import Window
import os
from functools import lru_cache



@lru_cache(maxsize=1)
def _embedder():
    return Embedder()                       # model is loaded once per process


@lru_cache(maxsize=2)
def _retriever(index_stamp: float) -> "Retriever":
    return Retriever()


def get_retriever() -> "Retriever":
    """Shared Retriever; rebuilt automatically if the index files change on disk."""
    ids_file = Store().ids_file
    stamp = os.path.getmtime(ids_file) if ids_file.exists() else 0.0
    return _retriever(stamp)

class Retriever:
    def __init__(self, store: Store | None = None, embedder=None):
        self.store = store or Store()
        self.embedder = embedder or _embedder()
        self.ids, self.vecs = self.store.load_vectors()
        if self.vecs is None or len(self.ids) == 0:
            raise SystemExit("The index is empty. Run: claims index")

    def search(self, query: str, k: int | None = None, context: int | None = None) -> list[Window]:
        """Best-matching sentences, each expanded to +/- `context` sentences, overlaps merged."""
        k = k or settings.top_k
        context = settings.context if context is None else context

        q = self.embedder.encode_query(query)
        scores = self.vecs @ q
        top = np.argsort(scores)[::-1][:k]

        hits = []   # (doc, idx, score, text)
        for i in top:
            doc, idx, text = self.store.sentence(int(self.ids[i]))
            hits.append((doc, idx, float(scores[i]), text))

        windows: list[Window] = []
        for doc, idx, score, text in sorted(hits, key=lambda h: (h[0], h[1])):
            lo, hi = max(0, idx - context), idx + context
            last = windows[-1] if windows else None
            if last and last.doc == doc and lo <= last.hi + 1:       # overlapping: merge
                last.hi = max(last.hi, hi)
                last.score = max(last.score, score)
                last.hit_sentences.append(text)
            else:
                windows.append(Window(doc, lo, hi, score, [text]))

        for w in windows:
            w.sentences = self.store.window_rows(w.doc, w.lo, w.hi)
        return sorted(windows, key=lambda w: -w.score)

