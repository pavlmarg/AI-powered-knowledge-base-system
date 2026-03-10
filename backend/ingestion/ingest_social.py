"""
ingestion/ingest_social.py
--------------------------
Layer 2 — Social Media Posts ingestion pipeline.

What this script does:
  1. Loads layer-2-social.json (146 records: Twitter + Reddit mixed)
  2. Extracts the ticker from the post content via cashtag regex ($TSLA)
     with a hashtag fallback (#TSLA) — there is NO dedicated ticker field
  3. Normalises the inconsistent engagement schema:
       Twitter → likes, retweets, views
       Reddit  → upvotes, comments
     Both are collapsed into a single float: engagement_score
  4. Normalises the ISO 8601 timestamp to a Unix integer
  5. Builds a metadata-prepended embed string:
       "[TSLA][Social][Twitter] <content>"
  6. Generates embeddings and upserts into 'layer_social' ChromaDB collection

Metadata stored per document:
  - ticker           : str   e.g. "TSLA"
  - layer            : str   always "social"
  - platform         : str   "Twitter" or "Reddit"
  - username         : str   original handle
  - engagement_score : float normalised engagement metric
  - date_ts          : int   Unix timestamp
  - date_str         : str   original date string, kept for display
"""

import json
import re
import uuid
from datetime import datetime

from core.config import (
    KNOWN_TICKERS,
    SOCIAL_FILE,
    TWITTER_WEIGHTS,
    REDDIT_WEIGHTS,
)
from ingestion.embedder import embed_texts
from retrieval.chroma_client import get_social_collection


def _parse_date(date_str: str) -> int:
    """Convert ISO 8601 string '2026-03-01T08:14:00Z' to Unix timestamp int."""
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    return int(dt.timestamp())


def _extract_ticker(content: str) -> str:
    """
    Extract ticker from post content.

    Strategy (in order of priority):
      1. Cashtag match:  $TSLA  — the standard financial social media format
      2. Hashtag match:  #TSLA  — used as fallback in some posts
      3. Returns 'UNKNOWN' if no known ticker found
    """
    # Search for $TICKER pattern first
    cashtags = re.findall(r"\$([A-Z]{1,5})", content)
    for tag in cashtags:
        if tag in KNOWN_TICKERS:
            return tag

    # Fallback: search for #TICKER pattern
    hashtags = re.findall(r"#([A-Z]{1,5})", content)
    for tag in hashtags:
        if tag in KNOWN_TICKERS:
            return tag

    return "UNKNOWN"


def _compute_engagement(record: dict) -> float:
    """
    Normalise platform-specific engagement into a single comparable score.

    Twitter formula : likes*1 + retweets*3 + views*0.01
    Reddit formula  : upvotes*1 + comments*2

    Weights are defined in config.py so they can be tuned without
    touching this file.
    """
    platform = record.get("platform", "")

    if platform == "Twitter":
        w = TWITTER_WEIGHTS
        return (
            record.get("likes", 0) * w["likes"]
            + record.get("retweets", 0) * w["retweets"]
            + record.get("views", 0) * w["views"]
        )
    elif platform == "Reddit":
        w = REDDIT_WEIGHTS
        return (
            record.get("upvotes", 0) * w["upvotes"]
            + record.get("comments", 0) * w["comments"]
        )
    return 0.0


def _build_embed_text(ticker: str, platform: str, content: str) -> str:
    """
    Prepend key metadata to the post content before embedding.
    Format: "[TSLA][Social][Twitter] <original post content>"
    """
    return f"[{ticker}][Social][{platform}] {content}"


def ingest_social() -> int:
    """
    Run the full Layer 2 ingestion pipeline.
    Returns the number of documents successfully ingested.
    """
    collection = get_social_collection()

    with open(SOCIAL_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    texts: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []

    skipped = 0
    for record in records:
        ticker   = _extract_ticker(record["content"])
        platform = record.get("platform", "Unknown")
        date_ts  = _parse_date(record["date"])
        engagement = _compute_engagement(record)

        # Log records where ticker could not be resolved
        if ticker == "UNKNOWN":
            skipped += 1
            print(f"[Social] ⚠️  Could not extract ticker from: {record['content'][:80]}")

        embed_text = _build_embed_text(ticker, platform, record["content"])

        texts.append(embed_text)
        metadatas.append({
            "ticker"           : ticker,
            "layer"            : "social",
            "platform"         : platform,
            "username"         : record.get("username", ""),
            "engagement_score" : engagement,
            "date_ts"          : date_ts,
            "date_str"         : record["date"],
        })
        ids.append(str(uuid.uuid5(uuid.NAMESPACE_DNS, embed_text)))

    print(f"[Social] Generating embeddings for {len(texts)} records...")
    embeddings = embed_texts(texts)

    print(f"[Social] Upserting into ChromaDB collection '{collection.name}'...")
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )

    print(f"[Social] ✅ Done — {len(ids)} documents ingested. ({skipped} with unknown ticker)")
    return len(ids)


if __name__ == "__main__":
    ingest_social()