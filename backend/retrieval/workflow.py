"""
retrieval/workflow.py
---------------------
Parallel retrieval workflow — fan-out / fan-in pattern.

Three entry points:

  seed_on_startup()
  ──────────────────
  Called once when FastAPI starts. Ingests news + Reddit buzz + SEC filings
  for all SEED_TICKERS if not already cached.

  retrieve_all(ticker, query)
  ────────────────────────────
  Single-ticker retrieval for any stock (seed or new).
  Fans out to 5 sources simultaneously:
    - Layer 1: News articles       (ChromaDB — auto-refreshed if stale)
    - Layer 2: Social media posts  (ChromaDB — static JSON)
    - Layer 3: SEC EDGAR filings   (ChromaDB — 10-K, 10-Q, 8-K, TTL 30 days)
    - Layer 4: Live market price   (Finnhub live API)
    - Layer 5: Reddit buzz         (ChromaDB — ApeWisdom, refreshed daily)

  run_cross_portfolio_retrieval(query, tickers_override=None)
  ────────────────────────────────────────────────────────────
  Fans out retrieve_all() across either:
    - tickers_override (list) — for COMPARISON queries with named tickers
    - all SEED_TICKERS        — for CROSS_PORTFOLIO / GENERAL queries
"""

import asyncio
from typing import Optional, List

from retrieval.retriever import retrieve_news, retrieve_social, retrieve_sec_filings, retrieve_reddit_buzz
from retrieval.finnhub_tool import get_live_price
from ingestion.ingest_news import ingest_news_if_stale
from ingestion.ingest_reddit_buzz import ingest_reddit_buzz_if_stale, ingest_reddit_buzz
from ingestion.ingest_social import ingest_social
from ingestion.ingest_sec import ingest_sec_if_stale, ingest_sec_for_ticker
from retrieval.chroma_client import get_social_collection, get_sec_collection
from core.config import SEED_TICKERS


# ── Startup seed ──────────────────────────────────────────────────────────────

async def seed_on_startup() -> None:
    """
    Ensure all SEED_TICKERS have fresh data across all layers in ChromaDB.
    Called from FastAPI's startup event (main.py lifespan hook).
    """
    # Layer 2 — Social: ingest once if collection is empty
    social_col = get_social_collection()
    if social_col.count() == 0:
        print("[Startup] Layer 2 (Social) — cold start, ingesting...")
        await asyncio.to_thread(ingest_social)
    else:
        print(f"[Startup] Layer 2 (Social) — already loaded ({social_col.count()} docs)")

    # Layer 3 — SEC filings: ingest per-ticker if stale
    sec_col = get_sec_collection()
    if sec_col.count() == 0:
        print("[Startup] Layer 3 (SEC) — cold start, ingesting all seed tickers...")
        await asyncio.to_thread(ingest_sec_for_ticker_all_seeds)
    else:
        print(f"[Startup] Layer 3 (SEC) — already loaded ({sec_col.count()} chunks)")

    # Layers 1 + 5 — News + Reddit Buzz: check staleness per ticker
    print(f"[Startup] Checking freshness for {len(SEED_TICKERS)} seed tickers...")
    tasks = [
        _ensure_news_fresh(ticker)
        for ticker in sorted(SEED_TICKERS)
    ] + [
        _ensure_reddit_buzz_fresh(ticker)
        for ticker in sorted(SEED_TICKERS)
    ]
    await asyncio.gather(*tasks)
    print("[Startup] ✅ All layers ready.")


def ingest_sec_for_ticker_all_seeds() -> None:
    """Synchronous helper to ingest SEC for all seed tickers sequentially."""
    for ticker in sorted(SEED_TICKERS):
        ingest_sec_for_ticker(ticker)


# ── Cache freshness checks ────────────────────────────────────────────────────

async def _ensure_news_fresh(ticker: str) -> None:
    count = await asyncio.to_thread(ingest_news_if_stale, ticker)
    if count > 0:
        print(f"[Workflow] 🔄 On-demand news ingestion: {count} new articles for {ticker}")


async def _ensure_reddit_buzz_fresh(ticker: str) -> None:
    count = await asyncio.to_thread(ingest_reddit_buzz_if_stale, ticker)
    if count > 0:
        print(f"[Workflow] 🔄 On-demand Reddit buzz ingestion for {ticker}")


async def _ensure_sec_fresh(ticker: str) -> None:
    count = await asyncio.to_thread(ingest_sec_if_stale, ticker)
    if count > 0:
        print(f"[Workflow] 🔄 On-demand SEC ingestion: {count} new chunks for {ticker}")


# ── Async retrieval wrappers ──────────────────────────────────────────────────

async def _fetch_news(ticker: str, query: str) -> list[dict]:
    return await asyncio.to_thread(retrieve_news, ticker, query)

async def _fetch_social(ticker: str, query: str) -> list[dict]:
    return await asyncio.to_thread(retrieve_social, ticker, query)

async def _fetch_sec(ticker: str, query: str) -> list[dict]:
    return await asyncio.to_thread(retrieve_sec_filings, ticker, query)

async def _fetch_price(ticker: str) -> dict:
    return await asyncio.to_thread(get_live_price, ticker)

async def _fetch_reddit_buzz(ticker: str, query: str) -> list[dict]:
    return await asyncio.to_thread(retrieve_reddit_buzz, ticker, query)


# ── Single-ticker retrieval ───────────────────────────────────────────────────

async def run_parallel_retrieval(ticker: str, query: str) -> dict:
    """
    Ensure fresh data then fan out across all 5 data layers concurrently.

    Step 1: Cache checks — ingest news, Reddit buzz, and SEC if stale.
            All three run in parallel since they write to different collections.
    Step 2: Fan-out — fire all 5 retrieval tasks simultaneously.
    Step 3: Fan-in — collect and return unified context dict.
    """
    # Step 1: ensure all caches are fresh in parallel
    await asyncio.gather(
        _ensure_news_fresh(ticker),
        _ensure_reddit_buzz_fresh(ticker),
        _ensure_sec_fresh(ticker),
    )

    print(f"[Workflow] Starting parallel retrieval for {ticker}...")

    # Step 2: fan-out across all 5 layers simultaneously
    news, social, sec_filings, price, reddit_buzz = await asyncio.gather(
        _fetch_news(ticker, query),
        _fetch_social(ticker, query),
        _fetch_sec(ticker, query),
        _fetch_price(ticker),
        _fetch_reddit_buzz(ticker, query),
    )

    print(f"[Workflow] ✅ {ticker} retrieved:")
    print(f"  News        : {len(news)} articles")
    print(f"  Social      : {len(social)} posts")
    print(f"  SEC Filings : {len(sec_filings)} chunks")
    print(f"  Reddit Buzz : {len(reddit_buzz)} signal(s)")
    print(f"  Price       : ${price.get('current_price', 'N/A')} "
          f"({'LIVE 🟢' if price.get('is_live') else 'MOCK/ERROR 🟡'})")

    return {
        "ticker"      : ticker,
        "query"       : query,
        "news"        : news,
        "social"      : social,
        "sec_filings" : sec_filings,
        "price"       : price,
        "reddit_buzz" : reddit_buzz,
    }


async def retrieve_all(ticker: str, query: str) -> dict:
    """
    Async entry point for single-ticker retrieval.
    Called by the FastAPI /query endpoint with await.
    """
    return await run_parallel_retrieval(ticker, query)


# ── Cross-portfolio / Comparison retrieval ────────────────────────────────────

async def run_cross_portfolio_retrieval(
    query: str,
    tickers_override: Optional[List[str]] = None,
) -> list[dict]:
    """
    Fan out retrieve_all() across a set of tickers simultaneously.

    Args:
        query            : The user's natural language question.
        tickers_override : If provided, retrieve only these specific tickers
                           (used for COMPARISON queries like "compare GME and NVDA").
                           If None, falls back to all SEED_TICKERS (cross-portfolio).

    Total latency ≈ one single retrieval regardless of ticker count,
    because all retrievals run concurrently.
    """
    target_tickers = sorted(tickers_override) if tickers_override else sorted(SEED_TICKERS)
    scope_label    = f"comparison ({', '.join(target_tickers)})" if tickers_override else f"full portfolio ({len(target_tickers)} tickers)"

    print(f"\n[Workflow] Cross-portfolio retrieval — scope: {scope_label}")

    contexts = await asyncio.gather(*[
        run_parallel_retrieval(ticker, query)
        for ticker in target_tickers
    ])

    total_news   = sum(len(c["news"])         for c in contexts)
    total_social = sum(len(c["social"])       for c in contexts)
    total_sec    = sum(len(c["sec_filings"])  for c in contexts)
    total_reddit = sum(len(c["reddit_buzz"])  for c in contexts)

    print(f"[Workflow] ✅ Retrieval complete.")
    print(f"  Tickers     : {[c['ticker'] for c in contexts]}")
    print(f"  News        : {total_news} total")
    print(f"  Social      : {total_social} total")
    print(f"  SEC Filings : {total_sec} total")
    print(f"  Reddit Buzz : {total_reddit} total")

    return list(contexts)


# ── Dev / Test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  [TEST A] Single-ticker retrieval (AAPL)")
    print("=" * 55)
    context = asyncio.run(retrieve_all("AAPL", "What are Apple's main risks?"))
    print(f"  News: {len(context['news'])} | Social: {len(context['social'])} | "
          f"SEC: {len(context['sec_filings'])} | Reddit: {len(context['reddit_buzz'])}")

    print("\n" + "=" * 55)
    print("  [TEST B] Comparison retrieval (GME vs NVDA)")
    print("=" * 55)
    contexts = asyncio.run(
        run_cross_portfolio_retrieval("Compare GME and NVDA", tickers_override=["GME", "NVDA"])
    )
    for c in contexts:
        print(f"  [{c['ticker']}] news={len(c['news'])} social={len(c['social'])} "
              f"sec={len(c['sec_filings'])} reddit={len(c['reddit_buzz'])}")

    print("\n" + "=" * 55)
    print("  [TEST C] Full cross-portfolio retrieval")
    print("=" * 55)
    contexts = asyncio.run(run_cross_portfolio_retrieval("Which stocks have the most SEC risk disclosures?"))
    for c in contexts:
        print(f"  [{c['ticker']}] news={len(c['news'])} social={len(c['social'])} "
              f"sec={len(c['sec_filings'])} reddit={len(c['reddit_buzz'])}")