"""
Embedder for the Project Documentation Knowledge Base.

Provides text embeddings using multiple providers with fallback:
1. Gemini direct API (primary)
2. OpenRouter API (secondary)  
3. Offline TF-IDF fallback (last resort)

Environment variables:
- GEMINI_API_KEY: API key for Gemini Embedding API
- OPENROUTER_API_KEY: API key for OpenRouter API

Usage:
    embedder = get_embedder()
    vectors, provider, dim = embedder.embed_texts(["text1", "text2"])
"""

import hashlib
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
try:
    from embedding_cache import EmbeddingCache, content_hash
except ImportError:
    EmbeddingCache = None
    content_hash = None
import math
from pathlib import Path
from typing import List, Tuple, Optional
import requests
from dotenv import load_dotenv

# Gemini: gemini-embedding-001 is the ONLY embedding model in the live
# Gemini API model list (2026-11-12). gemini-embedding-2 and
# text-embedding-004 do not exist there and are not coded for. Dim stays
# 3072 (model default); output_dimensionality is NOT used (see HANDOVER).
GEMINI_MODEL = 'gemini-embedding-001'
GEMINI_DIMENSION = 3072
GEMINI_BATCH_SIZE = 32
GEMINI_MAX_CONCURRENT_BATCHES = 2
OPENROUTER_MODEL = 'openai/text-embedding-3-small'
OPENROUTER_DIMENSION = 1536

# Load environment variables
load_dotenv()

class Embedder:
    """Text embedding service with provider fallback and caching."""
    
    def __init__(self, cache_path=None):
        self.provider: Optional[str] = None
        self.fitted: bool = False
        self.tfidf_vocabulary: Optional[List[float]] = None
        self.tfidf_idf: Optional[List[float]] = None
        self.dim: Optional[int] = None
        self.model_name: Optional[str] = None
        self.state_path: Path = Path(".doc-kb") / "tfidf.json"
        self.cache_path = cache_path
        self.cache = None
        self.last_task_types: list = []
        self.last_batch_sizes: list = []
        self.last_cache_hits = 0
        self.last_cache_misses = 0
        self._pace_lock = threading.Lock()
        self._last_call = 0.0
    def embed_texts(self, texts: List[str], task_type: str = "RETRIEVAL_DOCUMENT") -> Tuple[List[List[float]], str, int]:
        # Ingest chunks: RETRIEVAL_DOCUMENT; queries: RETRIEVAL_QUERY (embed_query).
        # The task type is sent to Gemini on every request; OpenRouter ignores it.
        if not texts:
            return [], self.provider or "", 0
        if self.provider is None:
            self._probe_providers()
        self.last_task_types = [task_type] * len(texts)
        cache = self._get_cache()
        if cache is not None:
            hashes = [content_hash(t) for t in texts]
            cached = cache.get_many(hashes)
            self.last_cache_hits = len(cached)
            miss_idx = [i for i, h in enumerate(hashes) if h not in cached]
            self.last_cache_misses = len(miss_idx)
            vectors = [cached.get(h) for h in hashes]
            if miss_idx:
                miss_vecs, _, _ = self._embed_uncached([texts[i] for i in miss_idx], task_type)
                cache.put_many({hashes[i]: miss_vecs[j] for j, i in enumerate(miss_idx)})
                for j, i in enumerate(miss_idx):
                    vectors[i] = miss_vecs[j]
            dim = self.dim or (len(vectors[0]) if vectors and vectors[0] else 0)
            return vectors, self.provider, dim
        return self._embed_uncached(texts, task_type)

    def _embed_uncached(self, texts, task_type):
        if self.provider == "gemini":
            return self._embed_gemini(texts, task_type)
        if self.provider == "openrouter":
            return self._embed_openrouter(texts)
        if self.provider == "local-tfidf":
            return self._embed_tfidf(texts)
        raise ValueError(f"Unknown provider: {self.provider}")

    def _get_cache(self):
        if not self.cache_path or EmbeddingCache is None:
            return None
        if self.provider not in ("gemini", "openrouter"):
            return None
        if self.cache is None:
            self.cache = EmbeddingCache(self.cache_path, self.model_name or self.provider, self.dim or 0)
        return self.cache
    def embed_query(self, text: str) -> Tuple[List[float], str, int]:
        vectors, provider, dim = self.embed_texts([text], task_type="RETRIEVAL_QUERY")
        return vectors[0], provider, dim
    def _probe_providers(self):
        try:
            self._test_gemini()
            self.provider = "gemini"
            self.model_name = GEMINI_MODEL
            self.dim = GEMINI_DIMENSION
            print("Using Gemini Embedding API", file=sys.stderr)
            return
        except Exception as e:
            print("Gemini API failed: {} (http status {})".format(type(e).__name__, getattr(getattr(e, "response", None), "status_code", None)), file=sys.stderr)
        try:
            self._test_openrouter()
            self.provider = "openrouter"
            self.model_name = OPENROUTER_MODEL
            self.dim = OPENROUTER_DIMENSION
            print("Using OpenRouter Embedding API", file=sys.stderr)
            return
        except Exception as e:
            print("OpenRouter API failed: {} (http status {})".format(type(e).__name__, getattr(getattr(e, "response", None), "status_code", None)), file=sys.stderr)
        self.provider = "local-tfidf"
        self.model_name = "local-tfidf"
        self.dim = None
        print("Using local TF-IDF fallback (no API available)", file=sys.stderr)
    def _test_gemini(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:batchEmbedContents"
        payload = {"requests": [{"model": f"models/{GEMINI_MODEL}", "content": {"parts": [{"text": "test"}]}, "taskType": "RETRIEVAL_DOCUMENT"}]}
        response = requests.post(url, json=payload, headers={"X-Goog-Api-Key": api_key, "Content-Type": "application/json"}, timeout=30)
        if response.status_code != 200:
            raise Exception(f"Gemini API returned {response.status_code}: {response.text[:200]}")
        embeddings = response.json().get("embeddings") or []
        if not embeddings or "values" not in embeddings[0]:
            raise Exception("Unexpected Gemini API response format")
        if len(embeddings[0]["values"]) != GEMINI_DIMENSION:
            raise Exception(f"Unexpected Gemini embedding dimension: {len(embeddings[0]['values'])}")

    def probe_output_dimensionality(self, dimension: int = 768):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return {"supported": False, "error": "GEMINI_API_KEY not set"}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:batchEmbedContents"
        payload = {"requests": [{"model": f"models/{GEMINI_MODEL}", "content": {"parts": [{"text": "test"}]}, "taskType": "RETRIEVAL_DOCUMENT", "outputDimensionality": dimension}]}
        try:
            response = requests.post(url, json=payload, headers={"X-Goog-Api-Key": api_key, "Content-Type": "application/json"}, timeout=30)
        except Exception as e:
            return {"supported": False, "error": str(e)}
        if response.status_code != 200:
            return {"supported": False, "status": response.status_code, "error": response.text[:200]}
        values = (response.json().get("embeddings") or [{}])[0].get("values") or []
        return {"supported": len(values) == dimension, "dimension": len(values), "status": response.status_code}
    def _test_openrouter(self):
        """Test OpenRouter Embedding API with a simple request."""
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        
        url = "https://openrouter.ai/api/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "openai/text-embedding-3-small",
            "input": ["test"]
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code != 200:
            raise Exception(f"OpenRouter API returned {response.status_code}: {response.text}")
        
        result = response.json()
        if "data" not in result:
            raise Exception("Unexpected OpenRouter API response format")
    
    def _embed_gemini(self, texts: List[str], task_type: str = "RETRIEVAL_DOCUMENT") -> Tuple[List[List[float]], str, int]:
        # Batch endpoint: 32 texts per request (API max 100), up to 2 batches
        # in flight, >=0.7s between request starts, exponential backoff on
        # 429/500/502/503/504 (up to 5 attempts, honours Retry-After).
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        self.model_name = GEMINI_MODEL
        self.dim = GEMINI_DIMENSION
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:batchEmbedContents"
        headers = {"X-Goog-Api-Key": api_key, "Content-Type": "application/json"}
        batches = [texts[i:i + GEMINI_BATCH_SIZE] for i in range(0, len(texts), GEMINI_BATCH_SIZE)]
        self.last_batch_sizes = [len(b) for b in batches]

        def post_batch(batch):
            payload = {"requests": [{"model": f"models/{GEMINI_MODEL}", "content": {"parts": [{"text": t}]}, "taskType": task_type} for t in batch]}
            last_error = None
            for attempt in range(5):
                with self._pace_lock:
                    wait = 0.7 - (time.time() - self._last_call)
                    if wait > 0:
                        time.sleep(wait)
                    self._last_call = time.time()
                try:
                    response = requests.post(url, json=payload, headers=headers, timeout=60)
                except requests.RequestException as e:
                    last_error = e
                    time.sleep(min(2 ** attempt * 2, 60))
                    continue
                if response.status_code == 200:
                    embeddings = response.json().get("embeddings") or []
                    if len(embeddings) != len(batch):
                        raise ValueError(f"Gemini returned {len(embeddings)} embeddings for {len(batch)} texts")
                    out = []
                    for e in embeddings:
                        vals = e.get("embedding", {}).get("values") if isinstance(e.get("embedding"), dict) else e.get("values")
                        out.append(list(vals))
                    return out
                if response.status_code in (429, 500, 502, 503, 504):
                    last_error = Exception(f"Gemini API returned {response.status_code}")
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else min(2 ** attempt * 2, 60)
                    time.sleep(delay)
                    continue
                raise Exception(f"Gemini API returned {response.status_code}: {response.text[:200]}")
            raise last_error or Exception("Gemini API failed after retries")

        if len(batches) == 1:
            vectors = post_batch(batches[0])
        else:
            with ThreadPoolExecutor(max_workers=GEMINI_MAX_CONCURRENT_BATCHES) as pool:
                results = list(pool.map(post_batch, batches))
            vectors = [v for batch_vecs in results for v in batch_vecs]
        return vectors, "gemini", GEMINI_DIMENSION
    def _embed_openrouter(self, texts: List[str]) -> Tuple[List[List[float]], str, int]:
        """Generate embeddings using OpenRouter API."""
        api_key = os.getenv("OPENROUTER_API_KEY")
        url = "https://openrouter.ai/api/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "openai/text-embedding-3-small",
            "input": texts
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code != 200:
            raise Exception(f"OpenRouter API returned {response.status_code}: {response.text}")
        
        result = response.json()
        if "data" not in result:
            raise Exception("Unexpected OpenRouter API response format")
        
        vectors = [item["embedding"] for item in result["data"]]
        
        # Extract dimension from first vector
        dim = len(vectors[0]) if vectors else 0
        self.dim = dim
        
        return vectors, "openrouter", dim
    
    def _embed_tfidf(self, texts: List[str]) -> Tuple[List[List[float]], str, int]:
        """Generate embeddings using local TF-IDF fallback."""
        # Load existing state if available
        if self.state_path.exists():
            self._load_state()
            self.fitted = True
        elif not self.fitted:
            # Fit on the texts passed to the first embed_texts call
            self._fit_tfidf(texts)
        
        vectors = []
        dim = 512
        
        for text in texts:
            # Tokenize text
            tokens = self._tokenize(text)
            
            # Compute TF-IDF vector
            vector = [0.0] * dim
            for token in tokens:
                # Get token hash index
                token_hash = hashlib.sha256(token.encode()).hexdigest()
                index = int(token_hash[:8], 16) % dim
                
                # Get TF-IDF weight
                if self.tfidf_idf and index < len(self.tfidf_idf):
                    vector[index] += self.tfidf_idf[index]
            
            # L2 normalize
            norm = math.sqrt(sum(x * x for x in vector))
            if norm > 0:
                vector = [x / norm for x in vector]
            
            vectors.append(vector)
        
        self.dim = dim
        return vectors, "local-tfidf", dim
    
    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text into lowercase word characters.

        CJK characters are also emitted one by one, so Chinese queries
        can match Chinese words: regex \w+ alone keeps a whole Chinese
        run as one token and would never match a single word like 鉴权.
        """
        import re
        tokens = re.findall(r'\w+', text.lower())
        out = list(tokens)
        for tok in tokens:
            cjk = [ch for ch in tok if '\u4e00' <= ch <= '\u9fff']
            if cjk:
                out.extend(cjk)
        return out
    
    def _fit_tfidf(self, texts: List[str]):
        """Fit TF-IDF model on training texts."""
        dim = 512
        all_tokens = []
        
        # Collect all tokens
        for text in texts:
            tokens = self._tokenize(text)
            all_tokens.extend(tokens)
        
        # Build vocabulary and compute IDF
        token_counts = {}
        doc_counts = {}
        
        for token in all_tokens:
            token_counts[token] = token_counts.get(token, 0) + 1
        
        # Simple IDF calculation: log((1+N)/(1+df)) + 1
        # where N is total number of tokens, df is document frequency
        # For simplicity, treat each unique token as a "document"
        unique_tokens = set(all_tokens)
        N = len(unique_tokens)
        
        self.tfidf_idf = []
        for i in range(dim):
            df = 0
            # In a real implementation, we would track document frequency
            # For this simplified version, use uniform IDF
            idf = math.log((1 + N) / (1 + 1)) + 1 if N > 0 else 1.0
            self.tfidf_idf.append(idf)
        
        self.fitted = True
    
    def save_state(self, path: Path):
        """Save TF-IDF state to JSON file."""
        if self.provider != "local-tfidf":
            print("Warning: save_state only applicable for local-tfidf provider", file=sys.stderr)
            return
        
        state = {
            "vocab": "hashing-512",
            "idf": self.tfidf_idf,
            "fitted": self.fitted
        }
        
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(state, f)
    
    def load_state(self, path: Path):
        """Load TF-IDF state from JSON file."""
        if not path.exists():
            print(f"Warning: State file not found at {path}", file=sys.stderr)
            return
        
        with open(path, 'r') as f:
            state = json.load(f)
        
        self.tfidf_idf = state.get("idf", [])
        self.fitted = state.get("fitted", False)


def get_embedder() -> Embedder:
    """Get a singleton Embedder instance."""
    return Embedder()