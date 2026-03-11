"""
ingestion/ingest_reddit_buzz.py
--------------------------------
Layer 5 — Reddit Buzz (ApeWisdom).

Completely independent from Layer 2 (social mock posts).
  - Different ChromaDB collection  : layer_reddit_buzz
  - Different document format      : quantitative signal text
  - Different IDs                  : uuid5, date-scoped per ticker
  - No shared state with any other layer

What ApeWisdom gives us (free, no API key):
  - rank          : current popularity rank across ~800 tracked tickers
  - mentions      : Reddit posts/comments mentioning this ticker (24h)
  - upvotes       : total upvotes on those posts (24h)
  - rank_24h_ago  : yesterday's rank — lets us compute momentum

What we store (1 document per ticker):
  Natural language text gpt-4.1 can reason about directly:

    "[GME][RedditBuzz] Reddit activity report (last 24h):
     Rank #3 across r/wallstreetbets and related subreddits
     (was #8 yesterday — rank improved by 5, trending: RISING).
     Mentioned 1,247 times with 9,840 upvotes in the past 24 hours."

Cache:
  TTL = REDDIT_BUZZ_CACHE_TTL_DAYS (default: 1 day).
  ID  = uuid5("reddit-buzz-{ticker}-{YYYY-MM-DD}") — deterministic and
  date-scoped so same-day re-ingest is a clean no-op upsert.

API:
  GET https://apewisdom.io/api/v1.0/filter/all-stocks/page/{n}
  No auth. ~8 pages × 100 results ≈ 800 tickers covered per walk.
"""

from __future__ import annotations

import uuid
import requests
from datetime import datetime, timezone, timedelta

from core.config import (
    APEWISDOM_URL,
    REDDIT_BUZZ_CACHE_TTL_DAYS,
    SEED_TICKERS,
)
from ingestion.embedder import embed_texts
from retrieval.chroma_client import get_reddit_buzz_collection


# ── ApeWisdom page walker ─────────────────────────────────────────────────────

def _fetch_all_apewisdom() -> dict[str, dict]:
    """
    Walk every ApeWisdom page and return a ticker-keyed dict.

    One HTTP walk covers all ~800 tracked tickers. We call this once per
    batch — never once per ticker — to avoid hammering the free API.

    Returns:
        { "GME": {"rank": 3, "mentions": 1247, "upvotes": 9840, "rank_24h_ago": 8} }
        Empty dict if the API is unreachable.
    """
    all_data: dict[str, dict] = {}
    page = 1

    while True:
        url = f"{APEWISDOM_URL}/page/{page}"
        try:
            resp = requests.get(url, timeout=10)

            if resp.status_code != 200:
                print(f"[RedditBuzz] ⚠️  HTTP {resp.status_code} on page {page} — stopping.")
                break

            body    = resp.json()
            results = body.get("results", [])
            pages   = int(body.get("pages", 1))

            for item in results:
                ticker = item.get("ticker", "").upper().strip()
                if ticker:
                    all_data[ticker] = {
                        "rank"        : int(item.get("rank", 0)),
                        "mentions"    : int(item.get("mentions", 0)),
                        "upvotes"     : int(item.get("upvotes", 0)),
                        "rank_24h_ago": int(item.get("rank_24h_ago", 0)),
                    }

            if page >= pages:
                break
            page += 1

        except requests.exceptions.Timeout:
            print(f"[RedditBuzz] ⚠️  Timeout on page {page} — stopping.")
            break
        except Exception as e:
            print(f"[RedditBuzz] ⚠️  Error on page {page}: {e} — stopping.")
            break

    print(f"[RedditBuzz] Fetched {len(all_data)} tickers ({page} page(s) walked).")
    return all_data


# ── Document builder ──────────────────────────────────────────────────────────

def _build_embed_text(ticker: str, data: dict) -> str:
    """
    Convert raw ApeWisdom stats into a natural language document.

    The format is deliberately descriptive so gpt-4.1 can extract:
      - momentum  (rising / falling / stable / new entry)
      - volume    (mention count)
      - conviction (upvote count)
    """
    rank     = data["rank"]
    rank_ago = data["rank_24h_ago"]
    mentions = data["mentions"]
    upvotes  = data["upvotes"]

    if rank_ago == 0:
        trend_desc = "new entry — not ranked yesterday"
        trend      = "NEW ENTRY"
    elif rank < rank_ago:
        diff       = rank_ago - rank
        trend_desc = f"rank improved by {diff} position{'s' if diff != 1 else ''}"
        trend      = "RISING"
    elif rank > rank_ago:
        diff       = rank - rank_ago
        trend_desc = f"rank dropped by {diff} position{'s' if diff != 1 else ''}"
        trend      = "FALLING"
    else:
        trend_desc = "rank unchanged from yesterday"
        trend      = "STABLE"

    return (
        f"[{ticker}][RedditBuzz] Reddit activity report (last 24h): "
        f"Rank #{rank} across r/wallstreetbets and related subreddits "
        f"(was #{rank_ago} yesterday — {trend_desc}, trending: {trend}). "
        f"Mentioned {mentions:,} times with {upvotes:,} upvotes in the past 24 hours."
    )


# ── Cache check ───────────────────────────────────────────────────────────────

def _is_reddit_buzz_fresh(ticker: str) -> bool:
    """Return True if a fresh Reddit buzz doc exists for this ticker."""
    try:
        collection = get_reddit_buzz_collection()
        cutoff_ts  = int(
            (datetime.now(timezone.utc) - timedelta(days=REDDIT_BUZZ_CACHE_TTL_DAYS))
            .timestamp()
        )
        results = collection.get(
            where={
                "$and": [
                    {"ticker" : {"$eq" : ticker}},
                    {"date_ts": {"$gte": cutoff_ts}},
                ]
            },
            limit=1,
        )
        fresh = len(results.get("ids", [])) > 0
        if fresh:
            print(f"[RedditBuzz] ✅ Cache fresh for {ticker} — skipping.")
        return fresh
    except Exception as e:
        print(f"[RedditBuzz] ⚠️  Cache check error for {ticker}: {e}")
        return False


# ── Core ingestion ────────────────────────────────────────────────────────────

def _ingest_one(ticker: str, data: dict) -> int:
    """Write one Reddit buzz document into layer_reddit_buzz collection."""
    collection = get_reddit_buzz_collection()
    now_ts     = int(datetime.now(timezone.utc).timestamp())
    today_str  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    embed_text = _build_embed_text(ticker, data)

    # Deterministic ID: one doc per ticker per calendar day.
    # Re-ingesting on the same day is a no-op (same ID → upsert = overwrite).
    doc_id    = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"reddit-buzz-{ticker}-{today_str}"))
    embedding = embed_texts([embed_text])[0]

    collection.upsert(
        ids        = [doc_id],
        embeddings = [embedding],
        documents  = [embed_text],
        metadatas  = [{
            "ticker"      : ticker,
            "layer"       : "reddit_buzz",
            "rank"        : data["rank"],
            "rank_24h_ago": data["rank_24h_ago"],
            "mentions"    : data["mentions"],
            "upvotes"     : data["upvotes"],
            "date_ts"     : now_ts,
            "date_str"    : today_str,
        }],
    )

    rank, rank_ago = data["rank"], data["rank_24h_ago"]
    arrow = "📈" if rank < rank_ago else ("📉" if rank > rank_ago else "➡️")
    print(
        f"[RedditBuzz] ✅ {ticker} — "
        f"Rank #{rank} {arrow} (was #{rank_ago}) | "
        f"{data['mentions']:,} mentions | {data['upvotes']:,} upvotes"
    )
    return 1


def ingest_reddit_buzz_if_stale(ticker: str) -> int:
    """
    On-demand cache-aware ingestion for a single ticker.

    Called by workflow.py before every query. Returns 0 immediately if
    cache is fresh. Walks ApeWisdom if stale but only processes one ticker.

    Works for any ticker (not just SEED_TICKERS).
    """
    if _is_reddit_buzz_fresh(ticker):
        return 0
    print(f"[RedditBuzz] Cache stale for {ticker} — fetching ApeWisdom...")
    all_data = _fetch_all_apewisdom()
    data = all_data.get(ticker)
    if not data:
        print(f"[RedditBuzz] ℹ️  {ticker} not ranked on ApeWisdom (low Reddit activity).")
        return 0
    return _ingest_one(ticker, data)


def ingest_reddit_buzz(tickers: list[str] | None = None) -> int:
    """
    Batch entry point — fetch ApeWisdom ONCE, ingest all tickers.

    Used by run_ingestion.py on startup and by POST /ingest.
    Skips tickers whose cache is still fresh.
    """
    targets = tickers if tickers is not None else list(SEED_TICKERS)
    stale   = [t for t in targets if not _is_reddit_buzz_fresh(t)]

    if not stale:
        print("[RedditBuzz] ✅ All tickers cache-fresh — nothing to ingest.")
        return 0

    print(f"[RedditBuzz] Fetching buzz for {len(stale)} stale ticker(s): {sorted(stale)}")
    all_data  = _fetch_all_apewisdom()
    total     = 0
    not_found = 0

    for ticker in stale:
        data = all_data.get(ticker)
        if data:
            total += _ingest_one(ticker, data)
        else:
            not_found += 1
            print(f"[RedditBuzz] ℹ️  {ticker} not ranked on ApeWisdom.")

    print(
        f"[RedditBuzz] ✅ Done — {total}/{len(stale)} ingested"
        + (f" ({not_found} not ranked)" if not_found else "")
    )
    return total


if __name__ == "__main__":
    count = ingest_reddit_buzz(["GME", "NVDA", "TSLA", "MSFT"])
    print(f"\nTotal ingested: {count}")