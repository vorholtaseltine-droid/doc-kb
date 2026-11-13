"""Vector store backends for the doc knowledge base.

Two backends behind one interface:
- Qdrant (default): qdrant-client in local persistent mode, data in
  <root>/.doc-kb/qdrant. No server, no Docker.
- SQLite: <root>/.doc-kb/vector.db, embeddings as float32 blobs, cosine
  similarity computed in Python with numpy.

Git remains the source of truth; either index is rebuildable with
`make ingest`. Backend is selected by env DOC_KB_BACKEND (qdrant|sqlite).
"""
import json
import os
import sqlite3
import struct
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

COLLECTION = "doc_kb"


def _point_id(payload: Dict[str, Any]) -> str:
    key = "{}#{}#{}".format(payload.get("path", ""), payload.get("heading_path", ""), payload.get("type", ""))
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def _result_dict(payload: Dict[str, Any], score: float) -> Dict[str, Any]:
    return {
        "path": payload.get("path", ""),
        "heading_path": payload.get("heading_path", ""),
        "module": payload.get("module", ""),
        "project_id": payload.get("project_id", ""),
        "commit_sha": payload.get("commit_sha", ""),
        "text": payload.get("text", ""),
        "type": payload.get("type", ""),
        "code_symbols": payload.get("code_symbols", []),
        "score": float(score),
    }


class QdrantStore:
    """Qdrant via qdrant-client local persistent mode (no server)."""

    backend = "qdrant"

    def __init__(self, root: Path, dim: int):
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        self.root = Path(root)
        self.dim = int(dim)
        self.data_dir = self.root / ".doc-kb" / "qdrant"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.client = QdrantClient(path=str(self.data_dir))
        self._VectorParams = VectorParams
        self._Distance = Distance
        self._ensure_collection()

    def _ensure_collection(self):
        try:
            info = self.client.get_collection(COLLECTION)
            existing = info.config.params.vectors.size
            if int(existing) != self.dim:
                self.client.delete_collection(COLLECTION)
                self.client.create_collection(
                    COLLECTION,
                    vectors_config=self._VectorParams(size=self.dim, distance=self._Distance.COSINE, on_disk=True),
                )
        except Exception:
            # Collection missing (or any lookup error) -> create it.
            try:
                self.client.create_collection(
                    COLLECTION,
                    vectors_config=self._VectorParams(size=self.dim, distance=self._Distance.COSINE, on_disk=True),
                )
            except Exception:
                pass

        self._ensure_payload_indexes()

    def recreate(self, dim: int):
        self.dim = int(dim)
        try:
            self.client.delete_collection(COLLECTION)
        except Exception:
            pass
        self._ensure_collection()

    def upsert(self, points: List[Dict[str, Any]]):
        from qdrant_client.models import PointStruct

        structs = []
        for p in points:
            payload = dict(p["payload"])
            structs.append(PointStruct(id=_point_id(payload), vector=list(p["vector"]), payload=payload))
        if structs:
            self.client.upsert(collection_name=COLLECTION, points=structs, wait=True)

    def delete_by_path(self, path: str):
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        ids = []
        offset = None
        while True:
            pts, offset = self.client.scroll(
                COLLECTION,
                scroll_filter=Filter(must=[FieldCondition(key="path", match=MatchValue(value=path))]),
                limit=256,
                offset=offset,
                with_payload=False,
            )
            ids.extend([pt.id for pt in pts])
            if offset is None:
                break
        if ids:
            self.client.delete(collection_name=COLLECTION, points_selector=ids, wait=True)

    def search(self, vector: List[float], top_k: int = 5, module: Optional[str] = None) -> List[Dict[str, Any]]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        qfilter = None
        if module:
            qfilter = Filter(must=[FieldCondition(key="module", match=MatchValue(value=module))])
        res = self.client.query_points(
            collection_name=COLLECTION,
            query=list(vector),
            limit=int(top_k),
            query_filter=qfilter,
            with_payload=True,
        )
        return [_result_dict(pt.payload or {}, pt.score) for pt in res.points]

    def count(self) -> int:
        return int(self.client.count(COLLECTION, exact=True).count)

    def close(self):
        try:
            self.client.close()
        except Exception:
            pass


    def _ensure_payload_indexes(self):
        # Payload indexes ONLY on project_id/module/commit_sha (the fields
        # used as filters). text/heading_path/type/code_symbols stay unindexed.
        from qdrant_client.models import PayloadSchemaType
        for field in ("project_id", "module", "commit_sha"):
            try:
                self.client.create_payload_index(collection_name=COLLECTION, field_name=field, field_schema=PayloadSchemaType.KEYWORD)
            except Exception:
                pass

    def fetch_all(self, module=None):
        # All stored chunks (for BM25), optionally filtered by module.
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        query_filter = None
        if module:
            query_filter = Filter(must=[FieldCondition(key="module", match=MatchValue(value=module))])
        results, offset = [], None
        while True:
            points, offset = self.client.scroll(collection_name=COLLECTION, scroll_filter=query_filter, limit=250, offset=offset, with_payload=True, with_vectors=False)
            results.extend(_result_dict(p.payload, 0.0) for p in points)
            if offset is None:
                break
        return results

class SQLiteStore:
    """SQLite vector store: embeddings as float32 blobs, cosine in Python."""

    backend = "sqlite"

    def __init__(self, root: Path, dim: int):
        self.root = Path(root)
        self.dim = int(dim)
        self.db_path = self.root / ".doc-kb" / "vector.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS chunks ("
            "id TEXT PRIMARY KEY, path TEXT, heading_path TEXT, module TEXT, "
            "commit_sha TEXT, type TEXT, text TEXT, code_symbols TEXT, vector BLOB)"
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path)")
        self.conn.commit()
        row = self.conn.execute("SELECT value FROM meta WHERE key='dim'").fetchone()
        if row is not None and int(row[0]) != self.dim:
            self.recreate(self.dim)
        else:
            self.conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('dim', ?)", (str(self.dim),))
            self.conn.commit()

    def recreate(self, dim: int):
        self.dim = int(dim)
        self.conn.execute("DROP TABLE IF EXISTS chunks")
        self.conn.execute(
            "CREATE TABLE chunks ("
            "id TEXT PRIMARY KEY, path TEXT, heading_path TEXT, module TEXT, "
            "commit_sha TEXT, type TEXT, text TEXT, code_symbols TEXT, vector BLOB)"
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_path ON chunks(path)")
        self.conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('dim', ?)", (str(self.dim),))
        self.conn.commit()

    def upsert(self, points: List[Dict[str, Any]]):
        for p in points:
            payload = dict(p["payload"])
            pid = _point_id(payload)
            vec = np.asarray(p["vector"], dtype=np.float32)
            self.conn.execute(
                "DELETE FROM chunks WHERE path=? AND heading_path=? AND type=?",
                (payload.get("path", ""), payload.get("heading_path", ""), payload.get("type", "")),
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO chunks "
                "(id, path, heading_path, module, commit_sha, type, text, code_symbols, vector) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    pid,
                    payload.get("path", ""),
                    payload.get("heading_path", ""),
                    payload.get("module", ""),
                    payload.get("commit_sha", ""),
                    payload.get("type", ""),
                    payload.get("text", ""),
                    json.dumps(payload.get("code_symbols", []), ensure_ascii=False),
                    vec.tobytes(),
                ),
            )
        self.conn.commit()

    def delete_by_path(self, path: str):
        self.conn.execute("DELETE FROM chunks WHERE path=?", (path,))
        self.conn.commit()

    def search(self, vector: List[float], top_k: int = 5, module: Optional[str] = None) -> List[Dict[str, Any]]:
        q = np.asarray(vector, dtype=np.float64)
        qn = np.linalg.norm(q)
        if qn == 0:
            return []
        q = q / qn
        if module:
            rows = self.conn.execute(
                "SELECT path, heading_path, module, commit_sha, type, text, code_symbols, vector "
                "FROM chunks WHERE module=?",
                (module,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT path, heading_path, module, commit_sha, type, text, code_symbols, vector FROM chunks"
            ).fetchall()
        scored = []
        for path, heading, mod, sha, typ, text, symbols, blob in rows:
            v = np.frombuffer(blob, dtype=np.float32).astype(np.float64)
            vn = np.linalg.norm(v)
            if vn == 0 or v.shape[0] != q.shape[0]:
                continue
            score = float(np.dot(q, v / vn))
            scored.append((score, {
                "path": path, "heading_path": heading, "module": mod,
                "commit_sha": sha, "text": text, "type": typ,
                "code_symbols": json.loads(symbols) if symbols else [],
            }))
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, payload in scored[: int(top_k)]:
            out.append(_result_dict(payload, score))
        return out

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


    def fetch_all(self, module=None):
        if module:
            rows = self.conn.execute("SELECT path, heading_path, module, commit_sha, text, type, code_symbols FROM chunks WHERE module=?", (module,)).fetchall()
        else:
            rows = self.conn.execute("SELECT path, heading_path, module, commit_sha, text, type, code_symbols FROM chunks").fetchall()
        out = []
        for path, heading_path, mod, sha, text, typ, symbols in rows:
            out.append({"path": path, "heading_path": heading_path, "module": mod, "project_id": "", "commit_sha": sha, "text": text, "type": typ, "code_symbols": json.loads(symbols) if symbols else [], "score": 0.0})
        return out

def open_store(root: Path, dim: int, backend: Optional[str] = None):
    """Open a vector store. backend: 'qdrant' (default) or 'sqlite'."""
    name = (backend or os.environ.get("DOC_KB_BACKEND", "qdrant")).lower()
    if name == "sqlite":
        return SQLiteStore(Path(root), int(dim))
    return QdrantStore(Path(root), int(dim))
