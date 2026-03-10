"""
ingestion/ingest_insider.py
---------------------------
Layer 3 — Insider Trading Records ingestion pipeline.

What this script does:
  1. Loads layer-3-insider.json (50 records)
  2. Applies the 'synthetic text transformation' pattern:
     Rather than embedding the raw transactional JSON, we construct a
     rich natural language sentence that preserves ALL structured fields
     while giving the embedding model dense, semantic text to work with.
     e.g. "[GME][Insider] CEO executed a SELL of 5,200,000 shares. <content>"
  3. Normalises the date-only format '2026-03-02' to Unix timestamp int
  4. Stores all structured fields as ChromaDB metadata for precise filtering
  5. Generates embeddings and upserts into 'layer_insider' ChromaDB collection

Metadata stored per document:
  - ticker          : str   e.g. "GME"  (already clean in source data)
  - layer           : str   always "insider"
  - executive_role  : str   "CEO", "CFO", "COO", etc.
  - action          : str   "BUY" or "SELL"
  - shares_volume   : int   number of shares traded
  - date_ts         : int   Unix timestamp — enables $gte/$lte range queries
  - date_str        : str   original date string, kept for display

Key architectural note:
  Layer 3 is the most valuable layer for contradiction detection.
  A CEO selling millions of shares while social sentiment is bullish
  is the exact signal the synthesis engine (Pillar 3) is designed to catch.
  Clean metadata here is critical for the CoT reasoning prompt.
"""

import json
import uuid
from datetime import datetime, timezone

from core.config import INSIDER_FILE
from ingestion.embedder import embed_texts
from retrieval.chroma_client import get_insider_collection


def _parse_date(date_str: str) -> int:
    """
    Convert date-only string '2026-03-02' to Unix timestamp int.
    Time is set to midnight UTC for consistency.
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _build_embed_text(
    ticker: str,
    executive_role: str,
    action: str,
    shares_volume: int,
    content: str,
) -> str:
    """
    Synthetic text transformation for structured insider trading records.

    Raw JSON fields are woven into a natural language sentence so that
    the embedding model captures the full semantic meaning of the transaction.

    Before: {"action": "SELL", "shares_volume": 5200000, ...}
    After:  "[GME][Insider] CEO executed a SELL of 5,200,000 shares. <content>"

    This ensures that queries like "executives selling stock" or
    "insider dumping shares" retrieve these records reliably.
    """
    formatted_shares = f"{shares_volume:,}"
    return (
        f"[{ticker}][Insider] {executive_role} executed a {action} "
        f"of {formatted_shares} shares. {content}"
    )


def ingest_insider() -> int:
    """
    Run the full Layer 3 ingestion pipeline.
    Returns the number of documents successfully ingested.
    """
    collection = get_insider_collection()

    with open(INSIDER_FILE, "r", encoding="utf-8") as f:
        records = json.load(f)

    texts: list[str] = []
    metadatas: list[dict] = []
    ids: list[str] = []

    for record in records:
        ticker         = record["ticker"]
        executive_role = record["executive_role"]
        action         = record["action"]
        shares_volume  = record["shares_volume"]
        content        = record["content"]
        date_ts        = _parse_date(record["date"])

        embed_text = _build_embed_text(
            ticker, executive_role, action, shares_volume, content
        )

        texts.append(embed_text)
        metadatas.append({
            "ticker"         : ticker,
            "layer"          : "insider",
            "executive_role" : executive_role,
            "action"         : action,
            "shares_volume"  : shares_volume,
            "date_ts"        : date_ts,
            "date_str"       : record["date"],
        })
        # Deterministic ID: prevents duplicates on re-ingestion
        ids.append(str(uuid.uuid5(uuid.NAMESPACE_DNS, embed_text)))

    print(f"[Insider] Generating embeddings for {len(texts)} records...")
    embeddings = embed_texts(texts)

    print(f"[Insider] Upserting into ChromaDB collection '{collection.name}'...")
    collection.upsert(
        ids=ids,
        embeddings=embeddings,
        documents=texts,
        metadatas=metadatas,
    )

    print(f"[Insider] ✅ Done — {len(ids)} documents ingested.")
    return len(ids)


if __name__ == "__main__":
    ingest_insider()