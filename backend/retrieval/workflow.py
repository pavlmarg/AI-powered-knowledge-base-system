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

  run_cross_portfolio_retrieval(query)
  ─────────────────────────────────────
  Fans out retrieve_all() across all SEED_TICKERS simultaneously.
  Used for cross-portfolio and general questions.

Layer 3 change:
  ingest_insider / retrieve_insider → ingest_sec / retrieve_sec_filings
  The static JSON with 50 fake trades is replaced by live SEC EDGAR filings.

Issue 2 fix:
  Replaced all asyncio.get_event_loop().run_in_executor() calls with
  asyncio.to_thread() — the modern Python 3.10+ idiomatic pattern.
  get_event_loop() is deprecated inside coroutines and raises
  DeprecationWarning in Python 3.12+.
"""

import asyncio
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

    Layer 1 (News)        — re-ingested if cache is stale (TTL: 7 days)
    Layer 2 (Social)      — ingested once on cold start; skipped on warm restart
    Layer 3 (SEC filings) — re-ingested if cache is stale (TTL: 30 days)
    Layer 5 (Reddit Buzz) — re-ingested if cache is stale (TTL: 1 day)
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
    """
    Before retrieval, check if news cache is stale and re-ingest if needed.
    This is what makes any new ticker work automatically on first query.
    """
    count = await asyncio.to_thread(ingest_news_if_stale, ticker)
    if count > 0:
        print(f"[Workflow] 🔄 On-demand news ingestion: {count} new articles for {ticker}")


async def _ensure_reddit_buzz_fresh(ticker: str) -> None:
    """
    Before retrieval, check if Reddit buzz cache is stale and re-ingest if needed.
    """
    count = await asyncio.to_thread(ingest_reddit_buzz_if_stale, ticker)
    if count > 0:
        print(f"[Workflow] 🔄 On-demand Reddit buzz ingestion for {ticker}")


async def _ensure_sec_fresh(ticker: str) -> None:
    """
    Before retrieval, check if SEC filings cache is stale and re-ingest if needed.
    TTL is 30 days — filings don't change often, but we want to catch new 10-Qs.
    """
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
        "sec_filings" : sec_filings,   # key renamed from "insider"
        "price"       : price,
        "reddit_buzz" : reddit_buzz,
    }


async def retrieve_all(ticker: str, query: str) -> dict:
    """
    Async entry point for single-ticker retrieval.
    Called by the FastAPI /query endpoint with await.
    """
    return await run_parallel_retrieval(ticker, query)


# ── Cross-portfolio retrieval ─────────────────────────────────────────────────

async def run_cross_portfolio_retrieval(query: str) -> list[dict]:
    """
    Fan out retrieve_all() across all SEED_TICKERS simultaneously.

    Used for cross-portfolio and general questions where no specific
    ticker was identified. All 10 retrievals run concurrently —
    total latency ~= one single retrieval.
    """
    print(f"\n[Workflow] Cross-portfolio retrieval across {len(SEED_TICKERS)} tickers...")

    contexts = await asyncio.gather(*[
        run_parallel_retrieval(ticker, query)
        for ticker in sorted(SEED_TICKERS)
    ])

    total_news   = sum(len(c["news"])         for c in contexts)
    total_social = sum(len(c["social"])       for c in contexts)
    total_sec    = sum(len(c["sec_filings"])  for c in contexts)
    total_reddit = sum(len(c["reddit_buzz"])  for c in contexts)

    print(f"[Workflow] ✅ Cross-portfolio complete.")
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
    print("  [TEST B] Cross-portfolio retrieval")
    print("=" * 55)
    contexts = asyncio.run(run_cross_portfolio_retrieval("Which stocks have the most SEC risk disclosures?"))
    for c in contexts:
        print(f"  [{c['ticker']}] news={len(c['news'])} social={len(c['social'])} "
              f"sec={len(c['sec_filings'])} reddit={len(c['reddit_buzz'])}")