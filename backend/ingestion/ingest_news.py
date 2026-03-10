"""
ingestion/ingest_news.py
------------------------
Layer 1 — News Articles ingestion pipeline.

What this script does:
  1. Loads layer-1-news-english.json (30 records)
  2. Extracts the real ticker from the noisy `tags` array by whitelisting
     against KNOWN_TICKERS — filters out noise like "AI", "Tariffs", "EV"
  3. Normalises the ISO 8601 timestamp to a Unix integer for ChromaDB
     range queries
  4. Builds a metadata-prepended text string for embedding:
       "[TSLA][News] New EU Tariffs Hit Tesla's Profit Margins — <content>"
  5. Generates embeddings via OpenAI text-embedding-3-small
  6. Upserts documents into the 'layer_news' ChromaDB collection

Metadata stored per document:
  - ticker      : str   e.g. "TSLA"
  - layer       : str   always "news"
  - date_ts     : int   Unix timestamp — enables $gte/$lte range queries
  - date_str    : str   human-readable original date, kept for display
  - title       : str   article headline
"""

import json
import uuid
from datetime import datetime, timezone

from core.config import KNOWN_TICKERS, NEWS_FILE
from ingestion.embedder import embed_texts
from retrieval.chroma_client import get_news_collection


def _parse_date(date_str: str) -> int:
    """Convert ISO 8601 string '2026-03-02T08:30:00Z' to Unix timestamp int."""
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    return int(dt.timestamp())


def _extract_ticker(tags: list[str]) -> str:
    """
    Return the first tag that matches a known ticker.
    Falls back to 'UNKNOWN' if none found (should not happen with clean data).
    """
    for tag in tags:
        if tag in KNOWN_TICKERS:
            return tag
    return "UNKNOWN"


def _build_embed_text(ticker: str, title: str, content: str) -> str:
    """
    Prepend key metadata to the content before embedding.
    This 'metadata-prepending' pattern gives a 10-20% precision boost
    as validated by the BAM Embeddings paper and FinanceBench benchmarks.
    """
    return f"[{ticker}][News] {title} — {content}"


def ingest_news() -> int:
    """
    Run the full Layer 1 ingestion pipeline.
    Returns the number of documents successfully ingested.
    """
    collection = get_news_collection()

    with open(NEWS_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    texts: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []

    for record in records:
        ticker   = _extract_ticker(record["tags"])
        date_ts  = _parse_date(record["date"])
        title    = record["title"]
        content  = record["content"]

        embed_text = _build_embed_text(ticker, title, content)

        texts.append(embed_text)
        metadatas.append({
            "ticker"   : ticker,
            "layer"    : "news",
            "date_ts"  : date_ts,
            "date_str" : record["date"],
            "title"    : title,
        })
        # Deterministic ID: prevents duplicate upserts on re-ingestion
        ids.append(str(uuid.uuid5(uuid.NAMESPACE_DNS, embed_text)))

    print(f"[News] Generating embeddings for {len(texts)} records...")
    embeddings = embed_texts(texts)

    print(f"[News] Upserting into ChromaDB collection '{collection.name}'...")
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )

    print(f"[News] ✅ Done — {len(ids)} documents ingested.")
    return len(ids)


if __name__ == "__main__":
    ingest_news()