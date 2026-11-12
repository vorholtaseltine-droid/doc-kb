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