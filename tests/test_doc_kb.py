"""Tests for the doc knowledge base. Run with: make test

Uses the real embedding API and the real vector store (no mocks).
setUpModule builds/refreshes the index once via incremental ingest.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import ingest
import kb


def setUpModule():
    report = ingest.run_ingest(PROJECT_ROOT, incremental=True)
    assert report["dim"] > 0, "ingest produced no embeddings: {}".format(report)


class TestDocKb(unittest.TestCase):
    def test_search_auth_returns_doc_and_code(self):
        """Search 'auth 模块怎么鉴权' -> auth doc first + a code path."""
        results = kb.search_docs("auth 模块怎么鉴权", top_k=5)
        paths = [r["path"] for r in results]
        self.assertGreaterEqual(len(results), 1, "no search results")
        self.assertTrue(
            results[0]["path"].endswith("docs/modules/auth/index.md"),
            "top result should be the auth doc, got: {}".format(paths),
        )
        self.assertTrue(
            any(r["path"].startswith("src/auth/") or "src/auth/jwt.py" in r["text"] for r in results),
            "no auth code path among top results: {}".format(paths),
        )

    def test_get_module_context(self):
        """get_module_context('auth') returns full context."""
        ctx = kb.get_module_context("auth")
        self.assertEqual(ctx["meta"]["owner"], "team-platform")
        self.assertEqual(ctx["meta"]["status"], "stable")
        self.assertTrue(
            any(d["path"].endswith("docs/modules/auth/index.md") and "鉴权" in d["content"] for d in ctx["docs"]),
            "auth index.md with 鉴权 missing from docs: {}".format([d["path"] for d in ctx["docs"]]),
        )
        self.assertTrue(
            any(c["path"] == "src/auth/jwt.py" for c in ctx["code"]),
            "src/auth/jwt.py missing from code: {}".format([c["path"] for c in ctx["code"]]),
        )
        self.assertTrue(
            any("verify_jwt" in c["symbols"] for c in ctx["code"]),
            "verify_jwt symbol missing from code context",
        )

    def test_incremental_ingest_only_changed(self):
        """Incremental ingest processes 0 files when nothing changed, 1 after one edit."""
        tmp = Path(tempfile.mkdtemp(prefix="doc-kb-fixture-"))
        try:
            shutil.copytree(PROJECT_ROOT / "docs", tmp / "docs")
            env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1")
            subprocess.run(["git", "init", "-q", str(tmp)], check=True, env=env)
            subprocess.run(["git", "-C", str(tmp), "config", "user.email", "test@example.com"], check=True, env=env)
            subprocess.run(["git", "-C", str(tmp), "config", "user.name", "test"], check=True, env=env)
            subprocess.run(["git", "-C", str(tmp), "add", "-A"], check=True, env=env)
            subprocess.run(["git", "-C", str(tmp), "commit", "-qm", "fixture"], check=True, env=env)
            first = ingest.run_ingest(tmp, incremental=False)
            self.assertGreater(first["processed"], 0, "full ingest processed nothing: {}".format(first))
            second = ingest.run_ingest(tmp, incremental=True)
            self.assertEqual(second["processed"], 0, "second incremental run should process 0 files: {}".format(second))
            idx = tmp / "docs" / "modules" / "auth" / "index.md"
            idx.write_text(idx.read_text(encoding="utf-8") + "\n## 新增小节\n内容补充。\n", encoding="utf-8")
            third = ingest.run_ingest(tmp, incremental=True)
            self.assertEqual(third["processed"], 1, "after one edit, incremental run should process 1 file: {}".format(third))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_write_doc_suggestion_writes_only_drafts(self):
        """Suggestions go to drafts/ and never modify docs/."""
        res = kb.write_doc_suggestion("docs/modules/auth/index.md", "# 建议\n测试内容", "test reason")
        self.assertTrue(res["draft_path"].startswith("drafts/"), res)
        draft = PROJECT_ROOT / res["draft_path"]
        try:
            self.assertTrue(draft.is_file(), "draft file was not created")
            self.assertIn("test reason", draft.read_text(encoding="utf-8"))
            self.assertFalse((PROJECT_ROOT / "docs/modules/auth/index.md").read_text(encoding="utf-8").endswith("测试内容"))
        finally:
            draft.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
