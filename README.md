# Project Documentation Knowledge Base & Developer Agent Bridge

A self‑contained knowledge base that bridges Git‑driven documentation with AI agents via a vector index, MCP server, and MkDocs site.

## Architecture

**Source of Truth:** Git (Markdown files + `meta.yaml`).

**Ingestion Pipeline (`ingest.py`):**
- Splits Markdown into heading‑level chunks (H1/H2/H3)
- Parses `meta.yaml` per module
- Extracts code symbols with Tree‑Sitter (Python/TypeScript) or regex fallback
- Generates embeddings (Gemini `embedding‑001` → OpenRouter `text‑embedding‑3‑small`)
- Stores vectors in a Qdrant local‑mode index (`.doc-kb/qdrant`) with SQLite fallback

**Vector Index:**
- Primary: Qdrant client in local persistent mode (data in `.doc-kb/qdrant`)
- Fallback: SQLite with vector column (when Qdrant unavailable)

**MCP Server (`mcp_server.py`):** Five tools:
1. `search_docs` – vector similarity search
2. `get_module_context` – retrieve chunk + surrounding docs + module meta
3. `list_changed_since` – Git diff against stored commit SHA
4. `get_auth_summary` – read auth module meta + code
5. `get_module_info` – read any module’s `meta.yaml`

**Coding Agent Bridge:** OpenCode can invoke the MCP server to query the knowledge base and retrieve context for development tasks.

**MkDocs Site:** Static documentation site (`site/`) with Material theme, hosting ADR, specs, runbooks, and module docs.

## Key Adaptations for This Box

- **No Docker / Ollama / Image Models:** Box has 4 vCPU / 7.7 GB RAM / 40 GB disk, no GPU, no Docker.
- **Embeddings:** Gemini Embedding API (`gemini‑embedding‑001`) with OpenRouter `text‑embedding‑3‑small` as fallback.
- **Agent:** OpenCode is the coding agent that uses the MCP server.

## Quickstart

```bash
# Install dependencies (once)
mkdir -p ~/.local/bin && pip install --user -r requirements.txt

# Initial full ingest (populates vector index)
make ingest INGEST_ARGS=--full

# Serve MkDocs site locally
make serve

# Run the MCP server (for OpenCode to connect)
make mcp

# Run unit tests (if any)
make test
```

## Scripts

- `Makefile` targets: `ingest`, `serve`, `mcp`, `test`, `build`, `hooks`, `help`.
- `.githooks/post-commit` automatically triggers incremental ingestion.
- `docker‑compose.yml` is a reference‑only file for local PCs (not used here).

## Project Layout

```
.docs-kb/
├── docs/                 # MkDocs source (index.md, adr/, specs/, runbooks/, modules/)
│   ├── adr/0001-use-qdrant.md
│   ├── specs/overview.md
│   ├── specs/ingest-pipeline.md
│   ├── runbooks/rebuild-index.md
│   ├── runbooks/query-mcp.md
│   └── modules/auth/index.md
├── src/                  # Python / TypeScript auth & JWT code
│   ├── auth/jwt.py
│   ├── auth/session.py
│   └── middleware/session.ts
├── ingest.py             # Vector index ingestion pipeline
├── mcp_server.py        # MCP server with 5 tools
├── requirements.txt
├── Makefile
├── .gitignore
└── .githooks/post-commit
```

See individual files for detailed specifications and procedures.
## Gemini embedding migration (2026-11-12)

- Model: gemini-embedding-001, dimension 3072 (the model default). It is the
  only embedding model in the live Gemini API model list (checked 2026-11-12);
  gemini-embedding-2 and text-embedding-004 do not exist there, so they are
  not coded for. outputDimensionality was verified to work for this model
  (768 requested -> 768-dim vector, HTTP 200) but is NOT used; the index stays
  at 3072 for now.
- Batching: batchEmbedContents, 32 texts per request (API max 100), up to 2
  batches in flight, >= 0.7s between request starts, exponential backoff on
  429/500/502/503/504 (up to 5 attempts, honours Retry-After). The key is sent
  only via the X-Goog-Api-Key header, never as ?key=. Never print or paste a key.
- task_type: RETRIEVAL_DOCUMENT for ingest chunks, RETRIEVAL_QUERY for
  search queries (see Embedder.embed_texts / embed_query).
- Cache: .doc-kb/embeddings_cache.db (SQLite, content hash -> float32 vector).
  Unchanged chunks skip the API. A model or dimension change clears the cache,
  and the collection manifest (manifest.json) records model + dimension; ingest
  recreates the collection when either mismatches.
- Chunk context prefix: [module: X] [type: Y] [title: Z] is prepended to chunk
  text before embedding (ingest.context_prefix); the stored chunk text is unchanged.
- Qdrant: vectors are stored on disk (on_disk=True). Payload indexes are
  created only for project_id, module and commit_sha; other payload fields
  stay unindexed. Note: local Qdrant ignores keyword payload indexes (it warns
  that they have no effect locally); filtering still works.
- Sensitive paths: a .sensitive file in the project root lists one fnmatch
  pattern per line (e.g. docs/internal/**, **/*.key). Matching docs and code
  are excluded from indexing and dropped from the manifest on the next ingest.
  .sensitive is git-ignored; copy .sensitive.example to create it. Never commit
  real sensitive paths.
- Search: kb.search_docs is hybrid - vector search (top 2*top_k) + BM25 over
  all stored chunks, fused with reciprocal rank fusion (k=60, bm25.py). Results
  carry a retrieval field (vector, bm25 or vector+bm25) and an RRF score.
  Query embeddings are pinned to the provider/dimension recorded in the manifest,
  so a query can never be embedded with a different dimension than the index.
- Chinese tokenization: CJK character-level (as in the TF-IDF fallback). jieba
  is NOT installed: plain and --user pip install jieba both fail with the PEP 668
  externally-managed-environment error. bm25.py uses jieba automatically if it is
  ever installed; until then this is a recorded gap, not a blocker.
- Quota: the Gemini daily quota (1,000 embed requests) was still exhausted on the
  evening of 2026-11-12 (probe passed once, batch embeds then 429'd persistently).
  The full rebuild is therefore pending the quota reset (around midnight PST).
  After midnight, run make ingest INGEST_ARGS=--full, confirm the manifest says
  provider: gemini, model: gemini-embedding-001, dim: 3072, then re-run
  make test and the two example searches in HANDOVER.md. See HANDOVER.md for details.
