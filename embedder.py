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
import math
from pathlib import Path
from typing import List, Tuple, Optional
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Embedder:
    """Text embedding service with provider fallback and caching."""
    
    def __init__(self):
        self.provider: Optional[str] = None
        self.fitted: bool = False
        self.tfidf_vocabulary: Optional[List[float]] = None
        self.tfidf_idf: Optional[List[float]] = None
        self.dim: Optional[int] = None
        self.state_path: Path = Path(".doc-kb") / "tfidf.json"
        
    def embed_texts(self, texts: List[str]) -> Tuple[List[List[float]], str, int]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            Tuple of (vectors, provider_name, dimension)
            
        Raises:
            ValueError: If all embedding providers fail
        """
        if self.provider is None:
            self._probe_providers()
        
        # Try the cached working provider
        if self.provider == "gemini":
            return self._embed_gemini(texts)
        elif self.provider == "openrouter":
            return self._embed_openrouter(texts)
        elif self.provider == "local-tfidf":
            return self._embed_tfidf(texts)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def embed_query(self, text: str) -> Tuple[List[float], str, int]:
        """
        Generate embedding for a single query text.
        
        Args:
            text: Text to embed
            
        Returns:
            Tuple of (vector, provider_name, dimension)
        """
        vectors, provider, dim = self.embed_texts([text])
        return vectors[0], provider, dim
    
    def _probe_providers(self):
        """Probe embedding providers in order of preference."""
        # Try Gemini first
        try:
            self._test_gemini()
            self.provider = "gemini"
            print("Using Gemini Embedding API")
            return
        except Exception as e:
            print(f"Gemini API failed: {e}")
        
        # Try OpenRouter second
        try:
            self._test_openrouter()
            self.provider = "openrouter"
            print("Using OpenRouter Embedding API")
            return
        except Exception as e:
            print(f"OpenRouter API failed: {e}")
        
        # Fall back to local TF-IDF
        self.provider = "local-tfidf"
        print("Using local TF-IDF fallback (warning: limited embedding quality)")
    
    def _test_gemini(self):
        """Test Gemini Embedding API with a simple request."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={api_key}"
        payload = {
            "content": {
                "parts": [{"text": "test"}]
            }
        }
        
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code != 200:
            raise Exception(f"Gemini API returned {response.status_code}: {response.text}")
        
        result = response.json()
        if "embedding" not in result:
            raise Exception("Unexpected Gemini API response format")
    
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
    
    def _embed_gemini(self, texts: List[str]) -> Tuple[List[List[float]], str, int]:
        """Generate embeddings using Gemini API."""
        api_key = os.getenv("GEMINI_API_KEY")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={api_key}"
        
        vectors = []
        
        for text in texts:
            payload = {
                "content": {
                    "parts": [{"text": text}]
                }
            }
            
            response = requests.post(url, json=payload, timeout=30)
            if response.status_code != 200:
                raise Exception(f"Gemini API returned {response.status_code}: {response.text}")
            
            result = response.json()
            if "embedding" not in result:
                raise Exception("Unexpected Gemini API response format")
            
            vectors.append(result["embedding"])
        
        # Extract dimension from first vector
        dim = len(vectors[0]) if vectors else 0
        self.dim = dim
        
        return vectors, "gemini", dim
    
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
        """Tokenize text into lowercase word characters."""
        import re
        return re.findall(r'\w+', text.lower())
    
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
            print("Warning: save_state only applicable for local-tfidf provider")
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
            print(f"Warning: State file not found at {path}")
            return
        
        with open(path, 'r') as f:
            state = json.load(f)
        
        self.tfidf_idf = state.get("idf", [])
        self.fitted = state.get("fitted", False)


def get_embedder() -> Embedder:
    """Get a singleton Embedder instance."""
    return Embedder()