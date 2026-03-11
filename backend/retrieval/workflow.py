"""
retrieval/workflow.py
---------------------
Parallel retrieval workflow — fan-out / fan-in pattern.

Three entry points:

  seed_on_startup()
  ──────────────────
  Called once when FastAPI starts. Ingests news for all SEED_TICKERS
  if not already cached. Guarantees the system always has data ready
  for the default watchlist before the first user query arrives.

  retrieve_all(ticker, query)
  ────────────────────────────
  Single-ticker retrieval for any stock (seed or new).
  Before retrieval, checks if news is stale and auto-ingests if needed.
  Fans out to 4 sources simultaneously:
    - Layer 1: News articles       (ChromaDB — auto-refreshed if stale)
    - Layer 2: Social media posts  (ChromaDB — static JSON for now)
    - Layer 3: Insider trades      (ChromaDB — static JSON for now)
    - Layer 4: Live market price   (Finnhub live API)

  run_cross_portfolio_retrieval(query)
  ─────────────────────────────────────
  Fans out retrieve_all() across all SEED_TICKERS simultaneously.
  Used for cross-portfolio and general questions.
  All 10 retrievals run in parallel — latency ~= one single retrieval.

Performance:
  Single-ticker sequential:    ~2.8s  →  parallel: ~0.8s
  Cross-portfolio sequential:  ~8.0s  →  parallel: ~0.8s
"""

import asyncio
from retrieval.retriever import retrieve_news, retrieve_social, retrieve_insider
from retrieval.finnhub_tool import get_live_price
from ingestion.ingest_news import ingest_news_if_stale
from core.config import SEED_TICKERS


# ── Startup seed ──────────────────────────────────────────────────────────────

async def seed_on_startup() -> None:
    """
    Ensure all SEED_TICKERS have fresh news in ChromaDB.

    Called from FastAPI's startup event. Runs ingestion for each seed
    ticker in parallel — only fetches from Finnhub if cache is stale.
    On a warm restart this completes in milliseconds (all cache hits).
    On a cold start it fetches and embeds news for all 10 tickers.
    """
    print(f"\n[Startup] Seeding {len(SEED_TICKERS)} tickers: {sorted(SEED_TICKERS)}")

    loop = asyncio.get_event_loop()

    async def _seed_one(ticker: str) -> None:
        count = await loop.run_in_executor(None, ingest_news_if_stale, ticker)
        if count > 0:
            print(f"[Startup] ✅ {ticker} — ingested {count} fresh articles")
        else:
            print(f"[Startup] ✅ {ticker} — cache already fresh")

    await asyncio.gather(*[_seed_one(t) for t in sorted(SEED_TICKERS)])
    print(f"[Startup] ✅ Seed complete — system ready.\n")


# ── On-demand ingestion check ─────────────────────────────────────────────────

async def _ensure_news_fresh(ticker: str) -> None:
    """
    Before retrieval, check if news cache is stale and re-ingest if needed.
    This is what makes any new ticker work automatically on first query.
    """
    loop  = asyncio.get_event_loop()
    count = await loop.run_in_executor(None, ingest_news_if_stale, ticker)
    if count > 0:
        print(f"[Workflow] 🔄 On-demand ingestion: {count} new articles for {ticker}")


# ── Async retrieval wrappers ──────────────────────────────────────────────────

async def _fetch_news(ticker: str, query: str) -> list[dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, retrieve_news, ticker, query)

async def _fetch_social(ticker: str, query: str) -> list[dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, retrieve_social, ticker, query)

async def _fetch_insider(ticker: str, query: str) -> list[dict]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, retrieve_insider, ticker, query)

async def _fetch_price(ticker: str) -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_live_price, ticker)


# ── Single-ticker retrieval ───────────────────────────────────────────────────

async def run_parallel_retrieval(ticker: str, query: str) -> dict:
    """
    Ensure fresh news then fan out across all 4 data layers concurrently.

    Step 1: Cache check — ingest news from Finnhub if stale (or first time).
    Step 2: Fan-out — fire all 4 retrieval tasks simultaneously.
    Step 3: Fan-in — collect and return unified context dict.

    Works for any ticker, not just seed tickers.
    """
    # Step 1: ensure news is fresh BEFORE retrieval
    # (must be sequential — retrieval reads what ingestion writes)
    await _ensure_news_fresh(ticker)

    print(f"[Workflow] Starting parallel retrieval for {ticker}...")

    # Step 2: fan-out across all 4 layers
    news, social, insider, price = await asyncio.gather(
        _fetch_news(ticker, query),
        _fetch_social(ticker, query),
        _fetch_insider(ticker, query),
        _fetch_price(ticker),
    )

    print(f"[Workflow] ✅ {ticker} retrieved:")
    print(f"  News     : {len(news)} articles")
    print(f"  Social   : {len(social)} posts")
    print(f"  Insider  : {len(insider)} trades")
    print(f"  Price    : ${price.get('current_price', 'N/A')} "
          f"({'LIVE 🟢' if price.get('is_live') else 'MOCK/ERROR 🟡'})")

    return {
        "ticker"  : ticker,
        "query"   : query,
        "news"    : news,
        "social"  : social,
        "insider" : insider,
        "price"   : price,
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
    ticker was identified. All 10 retrievals (including their cache
    checks) run concurrently — total latency ~= one single retrieval.

    Args:
        query: The user's natural language question.

    Returns:
        List of unified context dicts, one per seed ticker.
    """
    print(f"\n[Workflow] Cross-portfolio retrieval across {len(SEED_TICKERS)} tickers...")

    contexts = await asyncio.gather(*[
        run_parallel_retrieval(ticker, query)
        for ticker in sorted(SEED_TICKERS)
    ])

    total_news    = sum(len(c["news"])    for c in contexts)
    total_social  = sum(len(c["social"])  for c in contexts)
    total_insider = sum(len(c["insider"]) for c in contexts)

    print(f"[Workflow] ✅ Cross-portfolio complete.")
    print(f"  Tickers  : {[c['ticker'] for c in contexts]}")
    print(f"  News     : {total_news} total")
    print(f"  Social   : {total_social} total")
    print(f"  Insider  : {total_insider} total")

    return list(contexts)


# ── Dev / Test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  [TEST A] Single-ticker retrieval (MSFT — not in seed)")
    print("=" * 55)
    context = asyncio.run(retrieve_all("MSFT", "What is happening with Microsoft?"))
    print(f"  News: {len(context['news'])} | Social: {len(context['social'])} | Insider: {len(context['insider'])}")

    print("\n" + "=" * 55)
    print("  [TEST B] Cross-portfolio retrieval")
    print("=" * 55)
    contexts = asyncio.run(run_cross_portfolio_retrieval("Which stocks have the most insider selling?"))
    for c in contexts:
        print(f"  [{c['ticker']}] news={len(c['news'])} social={len(c['social'])} insider={len(c['insider'])}")