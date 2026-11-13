"""Ingest Markdown docs + code symbols into the vector index.

Git is the source of truth; the index is rebuildable at any time.
- Heading-level Markdown chunking (H1/H2/H3, heading_path kept).
- meta.yaml per module under docs/modules/*/meta.yaml.
- Code symbol extraction: tree-sitter when importable, else regex
  (Python + TypeScript).
- Embeddings: Embedder (Gemini -> OpenRouter -> local TF-IDF).
- Incremental rebuild via git diff + content hashes vs manifest.
- Index backend: Qdrant local mode (default) or SQLite (DOC_KB_BACKEND).
"""
import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

from embedder import Embedder
from vector_store import open_store
from sensitive import is_sensitive, load_sensitive_patterns

ROOT = Path(__file__).resolve().parent
STATE_DIRNAME = ".doc-kb"
MANIFEST_NAME = "manifest.json"
TFIDF_NAME = "tfidf.json"
HEADING_RE = re.compile(r"^(#{1,3})\s+(.*?)\s*$")
MAX_CHUNK = 4000


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(args, root: Path, **kw):
    try:
        r = subprocess.run(["git", "-C", str(root)] + args, capture_output=True, text=True, timeout=30, **kw)
        return r
    except Exception:
        return None


def get_commit_sha(root: Path) -> str:
    r = _git(["rev-parse", "HEAD"], root)
    if r and r.returncode == 0:
        return r.stdout.strip()
    return "uncommitted"


def chunk_markdown(text: str, path: str):
    """Split Markdown into heading-level chunks. Returns list of dicts."""
    lines = text.splitlines()
    chunks = []
    stack = []  # list of (level, title)
    cur_heading = None
    cur_body = []

    def flush():
        if cur_heading is None:
            return
        body = "\n".join(cur_body).strip()
        heading_path = " > ".join(t for _, t in stack)
        full = (cur_heading + "\n" + body).strip() if body else cur_heading.strip()
        if not full:
            return
        if len(full) > MAX_CHUNK:
            parts = re.split(r"\n\s*\n", full)
            buf = ""
            for part in parts:
                if len(buf) + len(part) + 2 > MAX_CHUNK and buf:
                    chunks.append({"heading_path": heading_path, "text": buf.strip()})
                    buf = part
                else:
                    buf = (buf + "\n\n" + part).strip() if buf else part
            if buf.strip():
                chunks.append({"heading_path": heading_path, "text": buf.strip()})
        else:
            chunks.append({"heading_path": heading_path, "text": full})

    for line in lines:
        m = HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            title = m.group(2)
            flush()
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            cur_heading = line
            cur_body = []
        else:
            if cur_heading is None:
                cur_heading = ""
                cur_body = [line]
            else:
                cur_body.append(line)
    flush()
    # Attach path-free chunks; the caller adds payload fields.
    return chunks


def _regex_symbols(text: str, lang: str):
    symbols = []
    for i, line in enumerate(text.splitlines(), start=1):
        name = None
        kind = "function"
        if lang == "py":
            m = re.match(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(", line)
            if m:
                name = m.group(1)
            else:
                m = re.match(r"^\s*class\s+(\w+)\s*[(:]", line)
                if m:
                    name, kind = m.group(1), "class"
        else:  # ts
            m = re.search(r"\bfunction\s+(\w+)\s*\(", line)
            if m:
                name = m.group(1)
            else:
                m = re.match(r"\s*class\s+(\w+)", line)
                if m:
                    name, kind = m.group(1), "class"
                else:
                    m = re.match(r"\s*(?:export\s+)?const\s+(\w+)\s*=.*=>", line)
                    if m:
                        name = m.group(1)
        if name:
            symbols.append({"name": name, "kind": kind, "line": i})
    return symbols


def extract_code_symbols(source_path: Path):
    """Extract function/class symbols from a .py/.ts file.

    Uses tree-sitter when importable, else regex. Returns a list of
    dicts {name, kind, line, preview}.
    """
    path = Path(source_path)
    text = path.read_text(encoding="utf-8", errors="ignore")
    suffix = path.suffix.lower()
    lang = "py" if suffix == ".py" else "ts"
    symbols = []
    try:
        from tree_sitter import Language, Parser

        if lang == "py":
            import tree_sitter_python as tsp
            language = Language(tsp.language())
        else:
            import tree_sitter_typescript as tst
            language = Language(tst.language_typescript())
        parser = Parser(language)
        tree = parser.parse(text.encode("utf-8"))
        lines = text.splitlines()

        def node_text(node):
            start = node.start_byte
            end = min(node.end_byte, start + 400)
            return text.encode("utf-8")[start:end].decode("utf-8", errors="ignore")

        def walk(node):
            if node.type in ("function_definition", "function_declaration", "function"):
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    symbols.append({
                        "name": node_text(name_node).strip(),
                        "kind": "function",
                        "line": node.start_point[0] + 1,
                        "preview": node_text(node).splitlines()[0][:160] if node_text(node) else "",
                    })
            elif node.type in ("class_definition", "class_declaration", "class"):
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    symbols.append({
                        "name": node_text(name_node).strip(),
                        "kind": "class",
                        "line": node.start_point[0] + 1,
                        "preview": node_text(node).splitlines()[0][:160] if node_text(node) else "",
                    })
            for child in node.children:
                walk(child)

        walk(tree.root_node)
        if symbols:
            for s in symbols:
                if not s.get("preview"):
                    ln = lines[s["line"] - 1] if 0 < s["line"] <= len(lines) else ""
                    s["preview"] = ln.strip()[:160]
            return symbols
    except Exception:
        pass
    out = []
    lines = text.splitlines()
    for s in _regex_symbols(text, lang):
        ln = lines[s["line"] - 1] if 0 < s["line"] <= len(lines) else ""
        s["preview"] = ln.strip()[:160]
        out.append(s)
    return out


def load_module_meta(root: Path):
    """Return {module_name: meta_dict} for docs/modules/*/meta.yaml."""
    metas = {}
    mods_dir = root / "docs" / "modules"
    if mods_dir.is_dir():
        for meta_path in sorted(mods_dir.glob("*/meta.yaml")):
            try:
                meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
            except Exception:
                meta = {}
            name = str(meta.get("module", meta_path.parent.name))
            metas[name] = meta
    return metas


def module_for_doc(relpath: str, metas):
    for name in metas:
        if relpath.startswith(f"docs/modules/{name}/"):
            return name
    return ""


def resolve_related_code(root: Path, meta):
    """Resolve a module meta's related_code entries to source files."""
    files = []
    for entry in meta.get("related_code", []) or []:
        entry = str(entry)
        if "*" in entry:
            files.extend(Path(m) for m in sorted(glob.glob(str(root / entry), recursive=True)))
        else:
            p = root / entry
            if p.is_file():
                files.append(p)
    out = []
    for p in files:
        if p.suffix.lower() in (".py", ".ts") and p.is_file():
            out.append(p)
    return out


def load_manifest(root: Path):
    p = root / STATE_DIRNAME / MANIFEST_NAME
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_manifest(root: Path, manifest):
    d = root / STATE_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    (d / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def context_prefix(point):
    title = point.get("heading_path") or point.get("path", "")
    return f"[module: {point.get('module', '')}] [type: {point.get('type', '')}] [title: {title}] {point.get('text', '')}"


def run_ingest(root, incremental: bool = True, backend=None):
    root = Path(root).resolve()
    state_dir = root / STATE_DIRNAME
    state_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(root)
    sensitive_patterns = load_sensitive_patterns(root)
    commit_sha = get_commit_sha(root)
    metas = load_module_meta(root)
    docs_dir = root / "docs"
    discovered_all = sorted(p for p in docs_dir.rglob("*.md") if "site" not in p.parts) if docs_dir.is_dir() else []
    excluded_sensitive = sorted(str(p.relative_to(root)) for p in discovered_all if is_sensitive(str(p.relative_to(root)), sensitive_patterns))
    discovered = [p for p in discovered_all if str(p.relative_to(root)) not in excluded_sensitive]
    relpaths = [str(p.relative_to(root)) for p in discovered]
    hashes = {rp: _sha256(root / rp) for rp in relpaths}
    manifest_files = manifest.get("files", {}) if isinstance(manifest, dict) else {}
    manifest_code = manifest.get("code_files", {}) if isinstance(manifest, dict) else {}
    full = (not incremental) or (not manifest)
    changed = []
    removed = []
    if full:
        changed = list(relpaths)
    else:
        changed_set = set()
        for rp in relpaths:
            if manifest_files.get(rp) != hashes[rp]:
                changed_set.add(rp)
        # git-diff signal (design doc mechanism), unioned with hashes.
        old_sha = manifest.get("commit_sha")
        if old_sha and old_sha != "uncommitted":
            r = _git(["diff", "--name-only", old_sha, "HEAD"], root)
            if r and r.returncode == 0:
                for line in r.stdout.splitlines():
                    line = line.strip()
                    if line in hashes:
                        changed_set.add(line)
        r = _git(["ls-files", "--others", "--exclude-standard", "docs"], root)
        if r and r.returncode == 0:
            for line in r.stdout.splitlines():
                line = line.strip()
                if line in hashes:
                    changed_set.add(line)
        changed = sorted(changed_set)
        removed = sorted(set(manifest_files) - set(relpaths))
    skipped = len(relpaths) - len(changed)
    # Code chunks belong to their module's index.md: regenerate when the
    # index file changed, or when any related source file changed.
    code_by_module = {}
    code_files_now = {}
    for name, meta in metas.items():
        srcs = resolve_related_code(root, meta)
        idx = f"docs/modules/{name}/index.md"
        regen = (not manifest) or (idx in changed)
        for src in srcs:
            rel = str(src.relative_to(root))
            if is_sensitive(rel, sensitive_patterns):
                continue
            h = _sha256(src)
            code_files_now[rel] = h
            if manifest_code.get(rel) != h:
                regen = True
        if regen:
            code_by_module[name] = srcs
    # Build chunks for changed docs + regenerated code chunks.
    doc_points = []
    pending_texts = []
    for rp in changed:
        text = (root / rp).read_text(encoding="utf-8", errors="ignore")
        mod = module_for_doc(rp, metas)
        for ch in chunk_markdown(text, rp):
            doc_points.append({
                "path": rp, "heading_path": ch["heading_path"],
                "module": mod, "commit_sha": commit_sha, "project_id": root.name,
                "text": ch["text"], "type": "doc", "code_symbols": [],
            })
    code_points = []
    for name, srcs in code_by_module.items():
        for src in srcs:
            rel = str(src.relative_to(root))
            if is_sensitive(rel, sensitive_patterns):
                continue
            hint = "auth 模块鉴权相关代码 " if rel.startswith("src/auth/") else ""
            for s in extract_code_symbols(src):
                code_points.append({
                    "path": rel, "heading_path": s["name"],
                    "module": name, "commit_sha": commit_sha, "project_id": root.name,
                    "text": "{}{} in {}: {}".format(hint, s["name"], rel, s.get("preview", "")),
                    "type": "code", "code_symbols": [s["name"]],
                })
    all_points = doc_points + code_points
    upserted = 0
    deleted = 0
    provider = manifest.get("provider", "") if isinstance(manifest, dict) else ""
    model = manifest.get("model", "") if isinstance(manifest, dict) else ""
    dim = manifest.get("dim") if isinstance(manifest, dict) else None
    backend_name = (backend or os.environ.get("DOC_KB_BACKEND", "qdrant")).lower()
    store = None
    final_count = manifest.get("chunk_count", 0)
    if all_points or removed or full:
        texts = [context_prefix(p) for p in all_points]
        embedder = Embedder(cache_path=state_dir / "embeddings_cache.db")
        if texts:
            vectors, provider, dim = embedder.embed_texts(texts)
            model = embedder.model_name or provider
        else:
            # No new chunks: keep the existing provider/dim.
            vectors = []
            if not dim:
                _, provider, dim = embedder.embed_texts(["probe"])
                model = embedder.model_name or model
        if provider == "local-tfidf":
            try:
                embedder.save_state(state_dir / TFIDF_NAME)
            except Exception as exc:
                print("warning: could not save tfidf state: {}".format(exc), file=sys.stderr)
        if provider == "local-tfidf":
            print("warning: using offline local-tfidf embeddings (no API key worked)", file=sys.stderr)
        store = open_store(root, int(dim), backend=backend_name)
        if manifest.get("dim") and int(manifest["dim"]) != int(dim):
            store.recreate(int(dim))
        if manifest.get("model") and manifest["model"] != model:
            store.recreate(int(dim))
        if manifest.get("backend") and manifest["backend"] != backend_name:
            store.recreate(int(dim))
        if full:
            store.recreate(int(dim))
        for rp in removed:
            store.delete_by_path(rp)
            deleted += 1
        for rp in changed:
            store.delete_by_path(rp)
        for src_rel in code_files_now:
            if any(src_rel == str(s.relative_to(root)) for srcs in code_by_module.values() for s in srcs):
                store.delete_by_path(src_rel)
        if all_points:
            for p, v in zip(all_points, vectors):
                p["vector"] = v
            store.upsert([{"vector": p.pop("vector"), "payload": p} for p in all_points])
            upserted = len(all_points)
        final_count = store.count()
        store.close()
    else:
        provider = provider or "unknown"
        dim = dim or 0
    new_manifest = {
        "commit_sha": commit_sha,
        "dim": int(dim) if dim else 0,
        "provider": provider,
        "model": model,
        "backend": backend_name,
        "files": hashes,
        "code_files": code_files_now,
        "chunk_count": 0,
    }
    if store is not None:
        new_manifest["chunk_count"] = final_count
    else:
        new_manifest["chunk_count"] = manifest.get("chunk_count", 0)
    save_manifest(root, new_manifest)
    return {
        "processed": len(changed),
        "skipped": skipped,
        "upserted": upserted,
        "deleted": deleted,
        "provider": provider,
        "dim": int(dim) if dim else 0,
        "backend": backend_name,
        "model": model,
        "excluded_sensitive": len(excluded_sensitive),
        "chunks": new_manifest["chunk_count"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ingest docs into the vector index.")
    ap.add_argument("--root", default=".", help="project root (default: .)")
    ap.add_argument("--full", action="store_true", help="force a full rebuild")
    ap.add_argument("--incremental", action="store_true", help="incremental ingest (default)")
    ap.add_argument("--backend", default=None, help="qdrant (default) or sqlite")
    args = ap.parse_args(argv)
    report = run_ingest(Path(args.root), incremental=not args.full, backend=args.backend)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
