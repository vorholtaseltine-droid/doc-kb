"""Query functions for the doc knowledge base (used by mcp_server.py
and by tests). Reads the index built by ingest.py; never writes docs."""
import json
import re
import subprocess
from pathlib import Path

from embedder import Embedder
from bm25 import bm25_scores, rrf_fuse, tokenize
from vector_store import open_store

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / ".doc-kb"
MANIFEST_PATH = STATE_DIR / "manifest.json"
TFIDF_PATH = STATE_DIR / "tfidf.json"


def _load_manifest(root: Path = ROOT):
    p = Path(root) / ".doc-kb" / "manifest.json"
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _git(root: Path, args):
    try:
        r = subprocess.run(["git", "-C", str(root)] + args, capture_output=True, text=True, timeout=30)
        return r
    except Exception as exc:
        raise ValueError("git failed: {}".format(exc))


def _open_read_store(root: Path = ROOT):
    manifest = _load_manifest(root)
    if not manifest:
        raise FileNotFoundError("index not built - run make ingest first")
    dim = int(manifest.get("dim") or 0)
    if not dim:
        raise FileNotFoundError("index not built - run make ingest first")
    return open_store(Path(root), dim, backend=manifest.get("backend", "qdrant")), manifest


def _embed_query_for_search(query: str, manifest):
    embedder = Embedder()
    provider = manifest.get("provider", "")
    if provider in ("gemini", "openrouter"):
        embedder.provider = provider
        embedder.dim = manifest.get("dim")
        embedder.model_name = manifest.get("model") or provider
    if provider == "local-tfidf":
        try:
            embedder.load_state(TFIDF_PATH)
        except Exception:
            pass
        # Force the query to use the SAME provider the index was built with;
        # otherwise the embedder would re-probe and pick an API provider
        # with a different embedding dimension.
        embedder.provider = "local-tfidf"
    vec, prov, dim = embedder.embed_query(query)
    return vec


def search_docs(query: str, project=None, module=None, top_k: int = 5):
    # Hybrid retrieval, actually wired: vector search (top 2*top_k) + BM25
    # over all stored chunks, fused with reciprocal rank fusion (k=60).
    # The query is embedded with task_type RETRIEVAL_QUERY (embed_query).
    # Returned score is the RRF fusion score; 'retrieval' says which leg(s)
    # ranked the chunk ('vector', 'bm25' or 'vector+bm25').
    root = Path(__file__).resolve().parent
    manifest_path = root / ".doc-kb" / "manifest.json"
    if not manifest_path.exists():
        raise RuntimeError("doc-kb index not found; run `make ingest` first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    store, _manifest = _open_read_store(root)
    try:
        vec = _embed_query_for_search(query, manifest)
        n = top_k * 2
        vector_results = store.search(vec, n, module=module)
        try:
            all_chunks = store.fetch_all(module=module)
        except Exception:
            all_chunks = []
        if not all_chunks:
            return vector_results[:top_k]
        query_tokens = tokenize(query)
        doc_tokens = [tokenize(c.get("text", "")) for c in all_chunks]
        scores = bm25_scores(query_tokens, doc_tokens)
        bm25_order = [i for i, s in sorted(enumerate(scores), key=lambda kv: -kv[1]) if s > 0][:n]
        def doc_key(c):
            return (c.get("path", ""), c.get("heading_path", ""), c.get("type", ""))
        vector_keys = [doc_key(r) for r in vector_results]
        bm25_keys = [doc_key(all_chunks[i]) for i in bm25_order]
        fused = rrf_fuse([vector_keys, bm25_keys], k=60)
        by_key = {}
        for r in vector_results:
            by_key.setdefault(doc_key(r), dict(r))
        for i in bm25_order:
            by_key.setdefault(doc_key(all_chunks[i]), dict(all_chunks[i]))
        out = []
        for key, rrf_score in fused[:top_k]:
            row = by_key[key]
            row["score"] = rrf_score
            if key in vector_keys and key in bm25_keys:
                row["retrieval"] = "vector+bm25"
            elif key in vector_keys:
                row["retrieval"] = "vector"
            else:
                row["retrieval"] = "bm25"
            out.append(row)
        return out
    finally:
        store.close()


def get_doc(path: str):
    """Return the full content of a file inside the repo."""
    if Path(path).is_absolute() or ".." in Path(path).parts:
        raise ValueError("path escapes the repo: {}".format(path))
    target = (ROOT / path).resolve()
    if not str(target).startswith(str(ROOT)):
        raise ValueError("path escapes the repo: {}".format(path))
    if not target.is_file():
        raise FileNotFoundError("no such doc: {}".format(path))
    rel = str(target.relative_to(ROOT))
    return {"path": rel, "content": target.read_text(encoding="utf-8", errors="ignore")}


def get_module_context(module: str):
    """Full context for one module: meta + docs + related code."""
    import yaml

    from ingest import extract_code_symbols, resolve_related_code

    mod_dir = ROOT / "docs" / "modules" / module
    meta_path = mod_dir / "meta.yaml"
    if not meta_path.is_file():
        raise FileNotFoundError("no such module: {}".format(module))
    meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    docs = []
    if mod_dir.is_dir():
        for p in sorted(mod_dir.glob("*.md")):
            docs.append({"path": str(p.relative_to(ROOT)), "content": p.read_text(encoding="utf-8", errors="ignore")})
    code = []
    for src in resolve_related_code(ROOT, meta):
        rel = str(src.relative_to(ROOT))
        lines = src.read_text(encoding="utf-8", errors="ignore").splitlines()
        symbols = [s["name"] for s in extract_code_symbols(src)]
        code.append({"path": rel, "content": "\n".join(lines[:200]), "symbols": symbols})
    return {"module": module, "meta": meta, "docs": docs, "code": code}


def list_changed_since(commit_or_time: str):
    """List files/commits changed since a commit ref or a time."""
    ref_ok = _git(ROOT, ["rev-parse", "--verify", commit_or_time])
    if ref_ok is not None and ref_ok.returncode == 0:
        r = _git(ROOT, ["diff", "--name-only", commit_or_time, "HEAD"])
        if r.returncode != 0:
            raise ValueError("git diff failed: {}".format(r.stderr.strip()[:300]))
        changed = sorted({l.strip() for l in r.stdout.splitlines() if l.strip()})
        log = _git(ROOT, ["log", "--pretty=format:%H|%ad|%s", "--date=short", "{}..HEAD".format(commit_or_time)])
        commits = []
        if log.returncode == 0:
            for line in log.stdout.splitlines():
                parts = line.split("|", 2)
                if len(parts) == 3:
                    commits.append({"sha": parts[0], "date": parts[1], "message": parts[2]})
        return {"changed": changed, "commits": commits}
    log = _git(ROOT, ["log", "--since={}".format(commit_or_time), "--name-only", "--pretty=format:COMMIT:%H|%ad|%s", "--date=short"])
    if log.returncode != 0:
        raise ValueError("git log failed (not a commit ref or a time?): {}".format(log.stderr.strip()[:300]))
    changed = set()
    commits = []
    cur = None
    for line in log.stdout.splitlines():
        if line.startswith("COMMIT:"):
            parts = line[len("COMMIT:"):].split("|", 2)
            if len(parts) == 3:
                cur = {"sha": parts[0], "date": parts[1], "message": parts[2]}
                commits.append(cur)
        elif line.strip():
            changed.add(line.strip())
    return {"changed": sorted(changed), "commits": commits}


def write_doc_suggestion(path: str, content: str, reason: str):
    """Write a doc suggestion ONLY to drafts/ (never into docs/)."""
    if not content or not content.strip():
        raise ValueError("content must not be empty")
    safe_reason = re.sub(r"\s+", " ", str(reason or "")).strip()
    drafts = ROOT / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    target = drafts / Path(path).name
    body = content.rstrip("\n") + "\n\n<!-- suggestion reason: {} -->\n".format(safe_reason)
    target.write_text(body, encoding="utf-8")
    return {"draft_path": str(target.relative_to(ROOT)), "reason": safe_reason, "path_requested": path}
