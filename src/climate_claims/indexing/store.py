import os
import sqlite3
from pathlib import Path

import numpy as np

from ..config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS docs(doc TEXT PRIMARY KEY, sha TEXT);
CREATE TABLE IF NOT EXISTS sentences(
    id INTEGER PRIMARY KEY, doc TEXT, idx INTEGER, page INTEGER,
    text TEXT, embedded INTEGER);
CREATE INDEX IF NOT EXISTS ix_doc_idx ON sentences(doc, idx);
"""
FILES = ("sentences.db", "vectors.npy", "ids.npy")


class Store:
    """SQLite (sentences, in reading order) + numpy (one vector per embedded sentence)."""

    def __init__(self, index_dir: Path | None = None):
        self.dir = Path(index_dir or settings.index_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.db_file = self.dir / "sentences.db"
        self.vecs_file = self.dir / "vectors.npy"
        self.ids_file = self.dir / "ids.npy"
        self.db = sqlite3.connect(self.db_file, check_same_thread=False)
        self.db.executescript(SCHEMA)

    @classmethod
    def wipe(cls, index_dir: Path | None = None) -> None:
        d = Path(index_dir or settings.index_dir)
        for name in FILES:
            (d / name).unlink(missing_ok=True)

    # ---- writing ----
    def insert_sentences(self, doc: str, rows: list[tuple]) -> None:
        """rows: (idx, page, text, embedded). Not committed until mark_done()."""
        self.db.executemany(
            "INSERT INTO sentences(doc, idx, page, text, embedded) VALUES(?,?,?,?,?)",
            [(doc, *r) for r in rows])

    def embeddable(self, doc: str) -> list[tuple[int, str]]:
        return self.db.execute(
            "SELECT id, text FROM sentences WHERE doc=? AND embedded=1 ORDER BY idx",
            (doc,)).fetchall()

    def save_vectors(self, ids: np.ndarray, vecs: np.ndarray) -> None:
        for path, arr in ((self.vecs_file, vecs), (self.ids_file, ids)):
            tmp = path.with_name(path.stem + ".tmp.npy")
            np.save(tmp, arr)
            os.replace(tmp, path)             # atomic: no half-written files

    def mark_done(self, doc: str, sha: str) -> None:
        """Commit. Called only AFTER the vectors are safely on disk."""
        self.db.execute("INSERT INTO docs VALUES(?,?)", (doc, sha))
        self.db.commit()

    # ---- reading ----
    def doc_hashes(self) -> dict[str, str]:
        return dict(self.db.execute("SELECT doc, sha FROM docs"))

    def load_vectors(self):
        """(ids, vecs), dropping vectors left over from an interrupted run."""
        if not self.ids_file.exists():
            return np.array([], dtype=np.int64), None
        ids, vecs = np.load(self.ids_file), np.load(self.vecs_file)
        valid = np.array([r[0] for r in self.db.execute(
            "SELECT id FROM sentences WHERE embedded=1")], dtype=np.int64)
        keep = np.isin(ids, valid)
        return ids[keep], vecs[keep]

    def sentence(self, sentence_id: int) -> tuple[str, int, str]:
        return self.db.execute(
            "SELECT doc, idx, text FROM sentences WHERE id=?", (sentence_id,)).fetchone()

    def window_rows(self, doc: str, lo: int, hi: int) -> list[tuple[int, str]]:
        return self.db.execute(
            "SELECT page, text FROM sentences WHERE doc=? AND idx BETWEEN ? AND ? ORDER BY idx",
            (doc, lo, hi)).fetchall()

    def stats(self) -> list[tuple[str, int, int]]:
        return self.db.execute(
            "SELECT doc, COUNT(*), COALESCE(SUM(embedded),0) FROM sentences GROUP BY doc").fetchall()