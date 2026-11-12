"""MCP server for the doc knowledge base (stdio transport).

Exposes exactly 5 tools, implemented in kb.py:
search_docs, get_doc, get_module_context, list_changed_since,
write_doc_suggestion. Suggestions are written ONLY to drafts/.
"""
from typing import Optional

from mcp.server.mcpserver import MCPServer

import kb

mcp = MCPServer("doc-kb")


@mcp.tool()
def search_docs(query: str, project: Optional[str] = None, module: Optional[str] = None, top_k: int = 5):
    """Semantic search over the docs and code index. Returns top_k chunks with path, heading_path, module, score and text."""
    return kb.search_docs(query, project=project, module=module, top_k=top_k)


@mcp.tool()
def get_doc(path: str):
    """Return the full content of one doc file (path relative to repo root)."""
    return kb.get_doc(path)


@mcp.tool()
def get_module_context(module: str):
    """Return full context for one module: meta.yaml, module docs and related code."""
    return kb.get_module_context(module)


@mcp.tool()
def list_changed_since(commit_or_time: str):
    """List files and commits changed since a git commit/ref or a time (e.g. '2026-11-01')."""
    return kb.list_changed_since(commit_or_time)


@mcp.tool()
def write_doc_suggestion(path: str, content: str, reason: str):
    """Write a doc suggestion ONLY to drafts/ (never into docs/). Returns the draft path."""
    return kb.write_doc_suggestion(path, content, reason)


if __name__ == "__main__":
    mcp.run()
