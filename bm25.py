"""BM25 lexical retrieval + reciprocal-rank fusion (RRF) with vector search.

Chinese tokenization: jieba is used when it is installed (it is not on this
box: plain ``pip install jieba`` and ``pip install --user jieba`` both fail
with the PEP 668 externally-managed-environment error, so jieba is an
optional dependency). The fallback is the character-level CJK tokenization
already used by the TF-IDF embedder: CJK runs become single characters,
Latin/CJK-mixed words stay whole, so e.g. ``auth`` and ``鉴权`` both match.
"""
from __future__ import annotations

import math
import re

try:
    import jieba as _jieba
except Exception:
    _jieba = None

JIEBA_AVAILABLE = _jieba is not None

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_TOKEN_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    if _jieba is not None:
        return [t.lower() for t in _jieba.cut(text) if t.strip()]
    tokens = []
    for word in _TOKEN_RE.findall(text.lower()):
        if _CJK_RE.search(word):
            tokens.extend(list(word))
        else:
            tokens.append(word)
    return tokens


def bm25_scores(query_tokens, doc_tokens_list, k1=1.5, b=0.75):
    n = len(doc_tokens_list)
    if n == 0:
        return []
    avg_len = sum(len(d) for d in doc_tokens_list) / n or 1
    df = {}
    for tokens in doc_tokens_list:
        for t in set(tokens):
            df[t] = df.get(t, 0) + 1
    scores = []
    for tokens in doc_tokens_list:
        tf = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        s = 0.0
        for t in set(query_tokens):
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            denom = tf[t] + k1 * (1 - b + b * len(tokens) / avg_len)
            s += idf * tf[t] * (k1 + 1) / denom
        scores.append(s)
    return scores


def rrf_fuse(ranked_lists, k=60):
    fused = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            fused[doc_id] = fused.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda kv: -kv[1])
