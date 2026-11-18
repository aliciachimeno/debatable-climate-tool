import numpy as np

from ..config import settings
from ..embedding import Embedder
from .loaders import file_sha256, iter_documents, read_pages
from .sentences import sentence_kind, split_pages
from .store import Store


def build_index(rebuild: bool = False) -> None:
    if rebuild:
        Store.wipe()
    store, embedder = Store(), Embedder()
    ids, vecs = store.load_vectors()
    done = store.doc_hashes()

    docs = iter_documents(settings.raw_dir)
    if not docs:
        print(f"No documents found in {settings.raw_dir}/")
        return

    for path in docs:
        doc, digest = path.name, file_sha256(path)
        if doc in done:
            if done[doc] != digest:
                raise SystemExit(f"{doc} changed since it was indexed. Run: claims index --rebuild")
            print(f"skip   {doc}")
            continue

        print(f"index  {doc}")
        sentences = split_pages(read_pages(path))
        if not sentences:
            print(f"       WARNING: no text extracted from {doc} (scanned PDF? needs OCR)")
        rows = [(i, page, text,
                 int(sentence_kind(text) == "body" and len(text.split()) >= settings.min_words))
                for i, (page, text) in enumerate(sentences)]
        store.insert_sentences(doc, rows)

        todo = store.embeddable(doc)
        if todo:
            new = embedder.encode([t for _, t in todo])
            new_ids = np.array([i for i, _ in todo], dtype=np.int64)
            vecs = new if vecs is None else np.vstack([vecs, new])
            ids = np.concatenate([ids, new_ids])
            store.save_vectors(ids, vecs)         # vectors first ...
        store.mark_done(doc, digest)              # ... then the DB commit
        print(f"       {len(rows)} sentences ({len(todo)} embedded)")

    print(f"Index holds {len(ids)} embedded sentences")