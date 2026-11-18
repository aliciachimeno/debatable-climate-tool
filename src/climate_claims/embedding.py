import numpy as np

from .config import settings

# bge models expect this prefix on queries (not on documents)
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder:
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.emb_model
        self._model = None

    @property
    def model(self):
        if self._model is None:                       # lazy: skipped indexes never load it
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(texts, normalize_embeddings=True, batch_size=64,
                                 show_progress_bar=len(texts) > 256).astype(np.float32)

    def encode_query(self, query: str) -> np.ndarray:
        return self.model.encode([QUERY_PREFIX + query],
                                 normalize_embeddings=True)[0].astype(np.float32)