"""SQLite cache: content hash -> embedding vector.

The cache key is sha256 of the exact text that was embedded (including
the chunk-context prefix), so a changed chunk or a changed prefix misses.
The model name and dimension are stored in a meta table; if either differs
from the cache's, all cached rows are dropped (a model/dimension change
must trigger a full re-embed) and the meta is updated.
"""
from __future__ import annotations

import hashlib
import sqlite3
import struct
from pathlib import Path


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingCache:
    def __init__(self, path, model: str, dimension: int):
        self.path = Path(path)
        self.model = model
        self.dimension = dimension
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS cache"
            " (content_hash TEXT PRIMARY KEY, vector BLOB NOT NULL)"
        )
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        self.cleared = self._validate_or_clear()

    def _meta(self, key):
        row = self.conn.execute(
            "SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def _validate_or_clear(self) -> bool:
        old_model = self._meta("model")
        old_dim = self._meta("dimension")
        if old_model in (None, self.model) and old_dim in (None, str(self.dimension)):
            self.conn.execute(
                "INSERT OR REPLACE INTO meta VALUES ('model', ?)", (self.model,))
            self.conn.execute(
                "INSERT OR REPLACE INTO meta VALUES ('dimension', ?)",
                (str(self.dimension),))
            self.conn.commit()
            return False
        self.conn.execute("DELETE FROM cache")
        self.conn.execute(
            "INSERT OR REPLACE INTO meta VALUES ('model', ?)", (self.model,))
        self.conn.execute(
            "INSERT OR REPLACE INTO meta VALUES ('dimension', ?)",
            (str(self.dimension),))
        self.conn.commit()
        return True

    @staticmethod
    def _pack(vector) -> bytes:
        return struct.pack(f"<{len(vector)}f", *vector)

    @staticmethod
    def _unpack(blob: bytes):
        return list(struct.unpack(f"<{len(blob) // 4}f", blob))

    def get_many(self, hashes):
        """Return {hash: vector} for the hashes present in the cache."""
        found = {}
        for h in hashes:
            row = self.conn.execute(
                "SELECT vector FROM cache WHERE content_hash=?", (h,)).fetchone()
            if row is not None:
                found[h] = self._unpack(row[0])
        return found

    def put_many(self, items):
        """Store {content_hash: vector} pairs."""
        self.conn.executemany(
            "INSERT OR REPLACE INTO cache VALUES (?, ?)",
            [(h, self._pack(v)) for h, v in items.items()],
        )
        self.conn.commit()

    def count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM cache").fetchone()
        return row[0] if row else 0

    def close(self):
        self.conn.close()
