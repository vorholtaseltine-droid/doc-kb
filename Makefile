# Project Documentation Knowledge Base & Developer Agent Bridge
# Box notes: 4 vCPU / 7.7 GB RAM, no GPU, no Docker, no Ollama.
# Qdrant runs in local persistent mode via qdrant-client (no server);
# DOC_KB_BACKEND=sqlite selects the SQLite fallback store.
# Git is the source of truth; the index is rebuildable any time.
.RECIPEPREFIX = >
SHELL := /bin/bash
export PATH := $(HOME)/.local/bin:$(PATH)
PYTHON := python3
INGEST_ARGS ?=

.PHONY: help ingest serve mcp test build hooks clean

help:  ## list targets
> @echo "Targets: ingest serve mcp test build hooks clean"
> @echo "  make ingest            incremental ingest (INGEST_ARGS=--full for full rebuild)"
> @echo "  make serve             mkdocs serve on 127.0.0.1:8000"
> @echo "  make mcp               run the MCP server (stdio)"
> @echo "  make test              run the test suite"
> @echo "  make build             build the static MkDocs site into site/"
> @echo "  make hooks             install the post-commit ingest hook"

ingest:  ## build/refresh the vector index (incremental by default)
> $(PYTHON) ingest.py $(INGEST_ARGS)

serve:  ## serve the MkDocs site locally
> mkdocs serve -a 127.0.0.1:8000

mcp:  ## run the MCP server (stdio transport)
> $(PYTHON) mcp_server.py

test:  ## run the test suite
> $(PYTHON) -m unittest discover -s tests -v

build:  ## build the static site into site/
> mkdocs build

hooks:  ## install the post-commit hook (incremental ingest on every commit)
> if [ -d .git ]; then cp .githooks/post-commit .git/hooks/post-commit && chmod +x .git/hooks/post-commit && echo "post-commit hook installed"; else echo "no .git directory"; fi

clean:  ## remove build artefacts and the (rebuildable) index
> rm -rf site __pycache__ tests/__pycache__ .doc-kb
