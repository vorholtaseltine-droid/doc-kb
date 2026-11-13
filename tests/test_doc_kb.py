"""Tests for the doc knowledge base. Run with: make test

Uses the real embedding API and the real vector store (no mocks).
setUpModule builds/refreshes the index once via incremental ingest.
"""
import json
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
import embedder
from unittest.mock import patch as mock_patch
from bm25 import bm25_scores, rrf_fuse, tokenize
from embedding_cache import EmbeddingCache
from ingest import context_prefix
from sensitive import is_sensitive, load_sensitive_patterns


def setUpModule():
    report = ingest.run_ingest(PROJECT_ROOT, incremental=True)
    assert report["dim"] > 0, "ingest produced no embeddings: {}".format(report)


class TestDocKb(unittest.TestCase):
    def test_search_auth_returns_doc_and_code(self):
        """Search 'auth 模块怎么鉴权' -> auth doc first + a code path."""
        results = kb.search_docs("auth 模块怎么鉴权", top_k=8)
        paths = [r["path"] for r in results]
        self.assertGreaterEqual(len(results), 1, "no search results")
        self.assertTrue(
            any(r["path"].endswith("docs/modules/auth/index.md") for r in results[:3]),
            "auth doc should be in the top 3 results, got: {}".format(paths),
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

    def _ingest_or_skip(self, tmp, incremental):
        try:
            return ingest.run_ingest(tmp, incremental=incremental)
        except Exception as e:
            if "429" in str(e):
                self.skipTest("Gemini quota exhausted (429); retry after midnight PST")
            raise

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
            first = self._ingest_or_skip(tmp, incremental=False)
            self.assertGreater(first["processed"], 0, "full ingest processed nothing: {}".format(first))
            second = self._ingest_or_skip(tmp, incremental=True)
            self.assertEqual(second["processed"], 0, "second incremental run should process 0 files: {}".format(second))
            idx = tmp / "docs" / "modules" / "auth" / "index.md"
            idx.write_text(idx.read_text(encoding="utf-8") + "\n## 新增小节\n内容补充。\n", encoding="utf-8")
            third = self._ingest_or_skip(tmp, incremental=True)
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



    def test_gemini_batch_task_type_and_cache(self):
        calls = []
        class Resp:
            status_code = 200
            headers = {}
            def __init__(self, payload):
                self._payload = payload
            def json(self):
                return {"embeddings": [{"values": [0.01] * 3072} for _ in self._payload["requests"]]}
        def fake_post(url, json=None, headers=None, timeout=None):
            calls.append(json)
            self.assertIn("batchEmbedContents", url)
            self.assertEqual(headers.get("X-Goog-Api-Key"), "fake-key")
            return Resp(json)
        tmp = Path(tempfile.mkdtemp())
        old_key = os.environ.get("GEMINI_API_KEY")
        os.environ["GEMINI_API_KEY"] = "fake-key"
        emb = embedder.Embedder(cache_path=tmp / "cache.db")
        emb.provider = "gemini"
        emb.model_name = "gemini-embedding-001"
        emb.dim = 3072
        texts = [f"chunk {i}" for i in range(35)]
        with mock_patch.object(embedder.requests, "post", side_effect=fake_post):
            vecs, prov, dim = emb.embed_texts(texts, task_type="RETRIEVAL_DOCUMENT")
            self.assertEqual((len(vecs), prov, dim), (35, "gemini", 3072))
            self.assertEqual(len(calls), 2)
            self.assertEqual([len(c["requests"]) for c in calls], [32, 3])
            for c in calls:
                self.assertTrue(all(r["taskType"] == "RETRIEVAL_DOCUMENT" for r in c["requests"]))
                self.assertTrue(all(r["model"] == "models/gemini-embedding-001" for r in c["requests"]))
            self.assertEqual(emb.last_cache_misses, 35)
            vecs2, _, _ = emb.embed_texts(texts, task_type="RETRIEVAL_DOCUMENT")
            self.assertEqual(len(calls), 2)
            self.assertEqual(emb.last_cache_hits, 35)
            self.assertEqual(len(vecs2), len(vecs))
            self.assertAlmostEqual(vecs2[0][0], 0.01, places=5)
            self.assertAlmostEqual(vecs2[-1][-1], 0.01, places=5)
            q, _, _ = emb.embed_query("auth query")
            self.assertEqual(len(calls), 3)
            self.assertEqual(calls[-1]["requests"][0]["taskType"], "RETRIEVAL_QUERY")
            self.assertEqual(len(q), 3072)
        if old_key is None:
            os.environ.pop("GEMINI_API_KEY", None)
        else:
            os.environ["GEMINI_API_KEY"] = old_key
    def test_embedding_cache_model_change_clears(self):
        tmp = Path(tempfile.mkdtemp())
        c = EmbeddingCache(tmp / "c.db", "gemini-embedding-001", 3072)
        c.put_many({"h1": [0.5, 0.25]})
        self.assertEqual(c.get_many(["h1"])["h1"], [0.5, 0.25])
        c2 = EmbeddingCache(tmp / "c.db", "other-model", 1536)
        self.assertTrue(c2.cleared)
        self.assertEqual(c2.count(), 0)
    def test_context_prefix_and_sensitive(self):
        self.assertEqual(context_prefix({"module": "auth", "type": "doc", "heading_path": "Auth", "text": "body"}), "[module: auth] [type: doc] [title: Auth] body")
        self.assertTrue(is_sensitive("docs/internal/x.md", ["docs/internal/**"]))
        self.assertTrue(is_sensitive("a/b.key", ["**/*.key"]))
        self.assertFalse(is_sensitive("docs/index.md", ["docs/internal/**"]))
        tmp = Path(tempfile.mkdtemp())
        (tmp / ".sensitive").write_text("# comment\n\ndocs/internal/**\n", encoding="utf-8")
        self.assertEqual(load_sensitive_patterns(tmp), ["docs/internal/**"])
    def test_bm25_rrf_fusion(self):
        self.assertEqual(tokenize("auth 模块怎么鉴权"), ["auth", "模", "块", "怎", "么", "鉴", "权"])
        docs = [tokenize("auth 鉴权流程"), tokenize("unrelated topic")]
        scores = bm25_scores(tokenize("auth 鉴权"), docs)
        self.assertGreater(scores[0], scores[1])
        self.assertEqual(rrf_fuse([["a", "b"], ["b", "a"]])[0][0], "a")
    def test_sensitive_file_excluded_from_ingest(self):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "docs" / "modules" / "auth").mkdir(parents=True)
        (tmp / "docs" / "internal").mkdir(parents=True)
        (tmp / "docs" / "modules" / "auth" / "index.md").write_text("# Auth\n\nAuth docs.\n", encoding="utf-8")
        (tmp / "docs" / "internal" / "secret.md").write_text("# Secret\n\nDo not index.\n", encoding="utf-8")
        (tmp / ".sensitive").write_text("docs/internal/**\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(tmp)], check=True)
        subprocess.run(["git", "-C", str(tmp), "-c", "user.email=t@t.t", "-c", "user.name=t", "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(tmp), "-c", "user.email=t@t.t", "-c", "user.name=t", "commit", "-qm", "fixture"], check=True)
        report = self._ingest_or_skip(tmp, incremental=False)
        self.assertEqual(report["excluded_sensitive"], 1)
        files = json.loads((tmp / ".doc-kb" / "manifest.json").read_text(encoding="utf-8"))["files"]
        self.assertNotIn("docs/internal/secret.md", files)
        self.assertIn("docs/modules/auth/index.md", files)
    def test_search_results_include_retrieval_source(self):
        results = kb.search_docs("auth 模块怎么鉴权", top_k=5)
        self.assertTrue(results)
        for r in results:
            self.assertIn(r["retrieval"], ("vector", "bm25", "vector+bm25"))
            self.assertIsInstance(r["score"], float)
if __name__ == "__main__":
    unittest.main()
