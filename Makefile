# Project Documentation Knowledge Base Makefile

# Make sure ~/.local/bin is in PATH for user-installed tools like mkdocs
export PATH := $(HOME)/.local/bin:$(PATH)

# Project variables
PROJECT_NAME := Project Documentation Knowledge Base
PYTHON := python3
MKDOCS := mkdocs
PIP := pip
PYTHON_PATH := $(HOME)/.local/lib/python3.10/site-packages

# Directory variables
DOCS_DIR := docs
SRC_DIR := src
VENV_DIR := .venv
DOCS_OUTPUT_DIR := site
DOC_KB_DIR := .doc-kb
INGEST_SCRIPT := ingest.py
MCP_SERVER := mcp_server.py
REQUIREMENTS_FILE := requirements.txt

# Default target
.PHONY: help
help:
	@echo "Available targets:"
	@echo "  make ingest         - Build vector index from Markdown documents (default: incremental)"
	@echo "  make ingest INGEST_ARGS=--full - Full rebuild of vector index"
	@echo "  make serve         - Serve MkDocs site locally (http://127.0.0.1:8000)"
	@echo "  make mcp           - Run MCP server for OpenCode connections"
	@echo "  make test          - Run unit tests"
	@echo "  make build         - Build static MkDocs site to $(DOCS_OUTPUT_DIR)/"
	@echo "  make hooks         - Install post-commit git hooks"
	@echo "  make clean         - Clean build artifacts and temporary files"
	@echo "  make deps          - Install Python dependencies"
	@echo "  make status        - Show project status and configuration"

# Default targets
.PHONY: default
run: serve

# Python dependencies
.PHONY: deps
 deps:
	@echo "Installing Python dependencies..."
	$(PIP) install --user -r $(REQUIREMENTS_FILE)

# Check if dependencies are installed
.PHONY: check-deps
check-deps:
	@echo "Checking dependencies..."
	@command -v mkdocs >/dev/null 2>&1 || (echo "mkdocs not found. Run: make deps" && exit 1)
	@command -v qdrant >/dev/null 2>&1 || echo "Warning: qdrant not in PATH"

# Ingestion targets
.PHONY: ingest
ingest: check-deps
	@echo "Building vector index..."
	@echo "Running: $(PYTHON) $(INGEST_SCRIPT) $(INGEST_ARGS)"
	$(PYTHON) $(INGEST_SCRIPT) $(INGEST_ARGS)

# Run ingest with full rebuild
.PHONY: ingest-full
ingest-full:
	@echo "Running full vector index rebuild..."
	make ingest INGEST_ARGS="--full"

.PHONY: ingest-incremental
ingest-incremental:
	@echo "Running incremental vector index build..."
	make ingest INGEST_ARGS="--incremental"

# Documentation serving targets
.PHONY: serve
serve: check-deps
	@echo "Serving MkDocs site on http://127.0.0.1:8000"
	$(MKDOCS) serve -a 127.0.0.1:8000

# Build static site
.PHONY: build
serve: build
build: check-deps
	@echo "Building static site to $(DOCS_OUTPUT_DIR)/"
	$(MKDOCS) build

# MCP server targets
.PHONY: mcp
mcp:
	@echo "Starting MCP server..."
	$(PYTHON) $(MCP_SERVER)

.PHONY: mcp-foreground
mcp-foreground:
	@echo "Starting MCP server in foreground mode..."
	make mcp

# Testing targets
.PHONY: test
test:
	@echo "Running unit tests..."
	$(PYTHON) -m unittest discover -s tests -v

# Hook targets
.PHONY: hooks
hooks:
	@echo "Installing git hooks..."
	@if [ -d ".githooks" ]; then \
		echo "Installing hooks from .githooks/"; \
		rm -rf .git/hooks; \
		cp -r .githooks/* .git/hooks; \
		chmod +x .git/hooks/*; \
		echo "Hooks installed successfully"; \
	else \
		echo "Error: .githooks directory not found"; \
		exit 1; \
	fi

# Clean targets
.PHONY: clean
clean:
	@echo "Cleaning build artifacts..."
	@rm -rf $(DOCS_OUTPUT_DIR)/*
	@rm -rf $(DOC_KB_DIR)
	@rm -rf *.pyc
	@rm -rf __pycache__/
	@rm -rf *.egg-info/
	@rm -rf dist/
	@rm -rf build/

.PHONY: clean-all
clean-all: clean
	@if [ -d "$(VENV_DIR)" ]; then \
		echo "Removing virtual environment..."; \
		rm -rf $(VENV_DIR); \
	fi

# Status targets
.PHONY: status
status:
	@echo "Project: $(PROJECT_NAME)"
	@echo "Status:"
	@echo "  Documentation: $(DOCS_DIR)/"
	@echo "  Source: $(SRC_DIR)/"
	@echo "  Vector index: $(DOC_KB_DIR)/"
	@echo "  Build output: $(DOCS_OUTPUT_DIR)/"
	@echo ""
	@echo "Configuration:"
	@python3 -c "
import os
import json
import sys

# Check for mkdocs.yml
if os.path.exists('mkdocs.yml'):
    print('  MkDocs: ✓')
else:
    print('  MkDocs: ✗')

# Check for requirements.txt
if os.path.exists('requirements.txt'):
    with open('requirements.txt') as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith('#')]
    print(f'  Dependencies ({len(lines)}): ✓')
else:
    print('  Dependencies: ✗')

# Check for key scripts
for script in ['ingest.py', 'mcp_server.py']:
    if os.path.exists(script):
        print(f'  {script}: ✓')
    else:
        print(f'  {script}: ✗')

# Check for docs directory
if os.path.exists('docs') and os.listdir('docs'):
    print('  Documentation: ✓')
else:
    print('  Documentation: ✗')
" 2>&1

# Health check targets
.PHONY: health
health:
	@echo "Running health checks..."
	@echo "Checking Python..."
	@python3 --version
	@echo "Checking MkDocs..."
	@mkdocs --version
	@echo "Checking Git..."
	@git --version
	@echo "Checking Qdrant client..."
	@python3 -c "from qdrant_client import QdrantClient; print('Qdrant client available')" 2>/dev/null || echo "Qdrant client not available"
	@echo "Health checks complete."

# Development targets
.PHONY: dev
dev: deps
	@echo "Setting up development environment..."
	@which python3 || (echo "Error: python3 not found. Please install Python 3.10+" && exit 1)
	@python3 --version | grep -q "3.10\|3.11\|3.12\|3.13" || (echo "Warning: Python 3.10+ recommended" && echo "Current version:" && python3 --version)
	@echo "Development environment ready."
	@echo "Use 'make help' to see available targets."

# Installation target
.PHONY: install
install: dev
	@echo "Installing and configuring project..."
	@echo "Run 'make hooks' to install git hooks."
	@echo "Run 'make ingest-full' to build vector index."
	@echo "Run 'make serve' to start documentation server."

# Version target
.PHONY: version
version:
	@echo "Project: $(PROJECT_NAME)"
	@echo "Version: 1.0.0"
	@if command -v git >/dev/null 2>&1; then \
		echo "Git version: $$(git --version 2>/dev/null || echo 'unknown')"; \
	fi
	@echo "Python version: $$(python3 --version 2>/dev/null || echo 'unknown')"
	@echo "MkDocs version: $$(mkdocs --version 2>/dev/null || echo 'unknown')"

# Display project information
.PHONY: info
info:
	@echo "========================================"
	@echo "$(PROJECT_NAME)"
	@echo "========================================"
	@echo "Description: A self-contained knowledge base that bridges Git-driven documentation with AI agents via a vector index, MCP server, and MkDocs site."
	@echo ""
	@echo "Key Features:"
	@echo "  - Git-driven documentation (source of truth)"
	@echo "  - Qdrant vector index with SQLite fallback"
	@echo "  - Gemini/OpenRouter embeddings"
	@echo "  - MCP server with 5 tools"
	@echo "  - MkDocs Material site"
	@echo "  - OpenCode integration"
	@echo ""
	@echo "Quick Start:"
	@echo "  1. Install dependencies: make deps"
	@echo "  2. Full rebuild: make ingest INGEST_ARGS=--full"
	@echo "  3. Serve docs: make serve"
	@echo "  4. Run MCP server: make mcp"
	@echo ""
	@echo "========================================"