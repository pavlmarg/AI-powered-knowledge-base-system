"""
retrieval/chroma_client.py
--------------------------
Single shared ChromaDB client used by both the ingestion pipeline (write)
and the retrieval workflow (read).

Returns one ChromaDB Collection object per data layer.
Collections are created with cosine similarity — optimal for text embeddings.

Layer 3 change:
  get_insider_collection() → get_sec_collection()
  COLLECTION_INSIDER       → COLLECTION_SEC
"""

from __future__ import annotations

import chromadb
from typing import Optional, Any

from core.config import (
    CHROMA_HOST,
    CHROMA_PORT,
    COLLECTION_NEWS,
    COLLECTION_SOCIAL,
    COLLECTION_SEC,
    COLLECTION_REDDIT_BUZZ,
)

# ── Client (singleton pattern) ────────────────────────────────────────────────
_client: Optional[Any] = None


def get_client() -> chromadb.HttpClient:
    global _client
    if _client is None:
        _client = chromadb.HttpClient(
            host=CHROMA_HOST,
            port=CHROMA_PORT,
        )
    return _client


# ── Collection helpers ────────────────────────────────────────────────────────
def get_collection(name: str) -> chromadb.Collection:
    """
    Get or create a ChromaDB collection by name.
    Uses cosine distance — the correct metric for normalised text embeddings.
    """
    client = get_client()
    return client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine"},
    )


def get_news_collection() -> chromadb.Collection:
    return get_collection(COLLECTION_NEWS)


def get_social_collection() -> chromadb.Collection:
    return get_collection(COLLECTION_SOCIAL)


def get_sec_collection() -> chromadb.Collection:
    """Layer 3 — SEC EDGAR filings (10-K, 10-Q, 8-K)."""
    return get_collection(COLLECTION_SEC)


def get_reddit_buzz_collection() -> chromadb.Collection:
    """Layer 5 — ApeWisdom Reddit buzz signals."""
    return get_collection(COLLECTION_REDDIT_BUZZ)


def reset_all_collections() -> None:
    """
    Drop and recreate all collections.
    Used by the POST /ingest endpoint to allow a clean re-ingestion.
    """
    client = get_client()
    for name in [COLLECTION_NEWS, COLLECTION_SOCIAL, COLLECTION_SEC, COLLECTION_REDDIT_BUZZ]:
        try:
            client.delete_collection(name)
        except Exception:
            pass 
    print("All collections reset.")