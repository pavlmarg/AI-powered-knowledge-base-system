"""
ingestion/ingest_news.py
------------------------
Layer 1 — News Articles ingestion pipeline.

UPGRADED from static JSON to live Finnhub /company-news API.

What this script does:
  1. Calls Finnhub's /company-news endpoint for a given ticker
     (or all SEED_TICKERS on startup)
  2. Filters articles to the configured NEWS_FETCH_DAYS window
  3. Builds a metadata-prepended text string for embedding:
       "[TSLA][News] New EU Tariffs Hit Tesla — <summary>"
  4. Generates embeddings via OpenAI text-embedding-3-small
  5. Upserts documents into the 'layer_news' ChromaDB collection

Why upsert and not insert:
  Deterministic IDs (uuid5 of content hash) mean re-running ingestion
  for the same ticker never creates duplicates — safe to call repeatedly
  on a schedule or on-demand.

Cache check:
  ingest_news_if_stale(ticker) checks ChromaDB first. If the ticker
  already has fresh documents (newer than NEWS_CACHE_TTL_DAYS) it skips
  the Finnhub call entirely. This makes on-demand ingestion cheap —
  the second query for any ticker costs nothing.

Metadata stored per document:
  - ticker    : str   e.g. "TSLA"
  - layer     : str   always "news"
  - date_ts   : int   Unix timestamp — enables $gte/$lte range queries
  - date_str  : str   human-readable date, kept for display
  - title     : str   article headline
  - source    : str   news source name e.g. "Reuters"
  - url       : str   original article URL
"""

import uuid
from datetime import datetime, timezone, timedelta

import finnhub

from core.config import (
    FINNHUB_API_KEY,
    NEWS_FETCH_DAYS,
    NEWS_CACHE_TTL_DAYS,
)
from ingestion.embedder import embed_texts
from retrieval.chroma_client import get_news_collection

# ── Finnhub client (singleton) ────────────────────────────────────────────────
_finnhub_client: finnhub.Client | None = None

def _get_finnhub() -> finnhub.Client:
    global _finnhub_client
    if _finnhub_client is None:
        _finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY)
    return _finnhub_client


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_embed_text(ticker: str, title: str, summary: str) -> str:
    """
    Prepend key metadata to the content before embedding.
    Metadata-prepending pattern gives 10-20% precision boost
    (validated by BAM Embeddings paper and FinanceBench benchmarks).
    """
    return f"[{ticker}][News] {title} — {summary}"


def _is_cache_fresh(ticker: str) -> bool:
    """
    Check if ChromaDB already has recent news for this ticker.

    Returns True if there is at least one document for the ticker
    with a date_ts newer than NEWS_CACHE_TTL_DAYS ago.
    Returning True means we can skip the Finnhub API call entirely.
    """
    try:
        collection = get_news_collection()
        cutoff_ts  = int(
            (datetime.now(timezone.utc) - timedelta(days=NEWS_CACHE_TTL_DAYS))
            .timestamp()
        )

        results = collection.get(
            where={
                "$and": [
                    {"ticker" : {"$eq"  : ticker}},
                    {"date_ts": {"$gte" : cutoff_ts}},
                ]
            },
            limit=1,   # We only need to know if at least one exists
        )

        has_fresh = len(results.get("ids", [])) > 0
        if has_fresh:
            print(f"[News] ✅ Cache fresh for {ticker} — skipping Finnhub fetch.")
        return has_fresh

    except Exception as e:
        print(f"[News] ⚠️  Cache check failed for {ticker}: {e} — will re-fetch.")
        return False


# ── Core ingestion ────────────────────────────────────────────────────────────

def ingest_news_for_ticker(ticker: str) -> int:
    """
    Fetch live news from Finnhub and upsert into ChromaDB for one ticker.

    This is the core function — always fetches from Finnhub regardless
    of cache state. Use ingest_news_if_stale() for cache-aware calls.

    Args:
        ticker: Stock ticker e.g. "TSLA", "MSFT", "AAPL"

    Returns:
        Number of documents upserted.
    """
    client     = _get_finnhub()
    collection = get_news_collection()

    # Calculate date window
    date_to   = datetime.now(timezone.utc)
    date_from = date_to - timedelta(days=NEWS_FETCH_DAYS)

    from_str = date_from.strftime("%Y-%m-%d")
    to_str   = date_to.strftime("%Y-%m-%d")

    print(f"[News] Fetching Finnhub news for {ticker} ({from_str} → {to_str})...")

    try:
        articles = client.company_news(ticker, _from=from_str, to=to_str)
    except Exception as e:
        print(f"[News] ⚠️  Finnhub fetch failed for {ticker}: {e}")
        return 0

    if not articles:
        print(f"[News] ⚠️  No articles returned for {ticker}.")
        return 0

    texts     : list[str]  = []
    metadatas : list[dict] = []
    ids       : list[str]  = []

    for article in articles:
        title   = article.get("headline", "").strip()
        summary = article.get("summary", "").strip()
        source  = article.get("source", "")
        url     = article.get("url", "")
        date_ts = article.get("datetime", 0)   # Finnhub returns Unix timestamp directly

        # Skip articles with no meaningful content
        if not title or not summary:
            continue

        # Convert Unix timestamp to human-readable string for display
        try:
            date_str = datetime.fromtimestamp(date_ts, tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
        except Exception:
            date_str = "Unknown"

        embed_text = _build_embed_text(ticker, title, summary)

        texts.append(embed_text)
        metadatas.append({
            "ticker"  : ticker,
            "layer"   : "news",
            "date_ts" : int(date_ts),
            "date_str": date_str,
            "title"   : title,
            "source"  : source,
            "url"     : url,
        })
        # Deterministic ID: prevents duplicates on re-ingestion
        ids.append(str(uuid.uuid5(uuid.NAMESPACE_DNS, embed_text)))

    if not texts:
        print(f"[News] ⚠️  All articles filtered out for {ticker} (missing title/summary).")
        return 0

    print(f"[News] Embedding {len(texts)} articles for {ticker}...")
    embeddings = embed_texts(texts)

    print(f"[News] Upserting into ChromaDB...")
    collection.upsert(
        ids        = ids,
        embeddings = embeddings,
        documents  = texts,
        metadatas  = metadatas,
    )

    print(f"[News] ✅ Done — {len(ids)} articles ingested for {ticker}.")
    return len(ids)


def ingest_news_if_stale(ticker: str) -> int:
    """
    Cache-aware ingestion — only fetches from Finnhub if needed.

    Called by the on-demand ingestion trigger in workflow.py before
    every query. Returns immediately with 0 if cache is still fresh,
    otherwise runs full ingestion and returns the count.

    Args:
        ticker: Stock ticker e.g. "TSLA"

    Returns:
        Number of new documents ingested (0 if cache was fresh).
    """
    if _is_cache_fresh(ticker):
        return 0
    return ingest_news_for_ticker(ticker)


def ingest_news(ticker: str | None = None) -> int:
    """
    Backwards-compatible entry point used by run_ingestion.py.

    If ticker is provided, ingests just that ticker.
    If ticker is None, ingests all SEED_TICKERS (startup behaviour).

    Returns total documents ingested.
    """
    from core.config import SEED_TICKERS

    if ticker:
        return ingest_news_for_ticker(ticker)

    # Startup: ingest all seed tickers
    total = 0
    for t in sorted(SEED_TICKERS):
        total += ingest_news_for_ticker(t)
    return total


if __name__ == "__main__":
    # Quick test — run with: python -m ingestion.ingest_news
    result = ingest_news_for_ticker("GME")
    print(f"\nIngested {result} articles for GME")