import numpy as np

from .store import Store


def check_index(samples: int = 3) -> None:
    store = Store()
    problems = []

    print("Documents:")
    for doc, total, emb in store.stats():
        print(f"  {doc}: {total} sentences, {emb} embedded")

    if not store.ids_file.exists():
        raise SystemExit("No vectors found. Run: claims index")

    ids, vecs = np.load(store.ids_file), np.load(store.vecs_file)      # raw, unpruned
    db_ids = {r[0] for r in store.db.execute("SELECT id FROM sentences WHERE embedded=1")}
    print(f"\nVectors: {vecs.shape}   IDs: {ids.shape}   embedded in DB: {len(db_ids)}")

    if not (len(vecs) == len(ids) == len(db_ids)):
        problems.append("vector / id / database counts do not match")
    if set(ids.tolist()) != db_ids:
        problems.append("ids.npy does not match the database")
    if np.isnan(vecs).any():
        problems.append("vectors contain NaN")
    if not np.allclose(np.linalg.norm(vecs, axis=1), 1, atol=1e-3):
        problems.append("vectors are not normalized")

    print("\nSample sentences:")
    for doc, idx, page, text in store.db.execute(
            "SELECT doc, idx, page, text FROM sentences WHERE embedded=1 "
            f"ORDER BY RANDOM() LIMIT {int(samples)}"):
        print(f"  [{doc}, p.{page}, #{idx}] {text}")

    if problems:
        print("\nPROBLEMS:", *problems, sep="\n  - ")
        raise SystemExit("Fix with: claims index --rebuild")
    print("\nAll checks passed.")