"""Sensitive-path exclusion for ingest.

A ``.sensitive`` file in the project root lists one path pattern per line
(gitignore-style, matched with :mod:`fnmatch` against the repo-relative
path, e.g. ``docs/internal/**`` or ``**/*.key``). Lines starting with ``#``
and blank lines are ignored. ``.sensitive`` itself is git-ignored;
only ``.sensitive.example`` is committed, so real sensitive paths are
never written into the repo.
"""
from __future__ import annotations

import fnmatch
from pathlib import Path

SENSITIVE_FILENAME = ".sensitive"


def load_sensitive_patterns(root) -> list[str]:
    """Return the patterns from ``<root>/.sensitive`` (empty if absent)."""
    path = Path(root) / SENSITIVE_FILENAME
    if not path.exists():
        return []
    patterns = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def is_sensitive(rel_path: str, patterns) -> bool:
    """True if *rel_path* matches a pattern (repo-relative, ``/``-separated)."""
    rel = str(rel_path).replace("\\", "/").strip("/")
    for pattern in patterns:
        pat = pattern.strip().strip("/")
        if not pat:
            continue
        if fnmatch.fnmatch(rel, pat):
            return True
        if fnmatch.fnmatch(rel, pat.rstrip("/") + "/**"):
            return True
        parts = rel.split("/")
        for i in range(1, len(parts)):
            if fnmatch.fnmatch("/".join(parts[:i]), pat):
                return True
    return False
