"""
retrieval/workflow.py
---------------------
Parallel retrieval workflow using LlamaIndex async events.

Architecture — Fan-Out / Fan-In pattern:
  1. A single StartEvent triggers 4 concurrent retrieval tasks
  2. All 4 tasks run simultaneously via asyncio (no blocking)
  3. A CollectEvent aggregates results as they arrive
  4. Once all 4 are done a StopEvent returns the unified context

The 4 parallel data sources:
  - Layer 1: News articles       (ChromaDB semantic search)
  - Layer 2: Social media posts  (ChromaDB semantic search)
  - Layer 3: Insider trades      (ChromaDB semantic search)
  - Layer 4: Live market price   (Finnhub REST API)

Why parallel matters:
  Sequential:  news(800ms) + social(800ms) + insider(800ms) + price(400ms) = ~2.8s
  Parallel:    max(800ms, 800ms, 800ms, 400ms)                             = ~0.8s

  3.5x faster — critical for a responsive demo.

Output — a single unified context dict:
  {
    "ticker"  : "GME",
    "query"   : "What is happening with GME?",
    "news"    : [ ... list of retrieved news docs ],
    "social"  : [ ... list of retrieved social posts ],
    "insider" : [ ... list of retrieved insider trades ],
    "price"   : { ... live price data from Finnhub },
  }

This context dict is passed directly to the synthesis engine (Phase 3).
"""

import asyncio
from retrieval.retriever import retrieve_news, retrieve_social, retrieve_insider
from retrieval.finnhub_tool import get_live_price


async def _fetch_news(ticker: str, query: str) -> list[dict]:
    """Async wrapper for news retrieval."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, retrieve_news, ticker, query)


async def _fetch_social(ticker: str, query: str) -> list[dict]:
    """Async wrapper for social retrieval."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, retrieve_social, ticker, query)


async def _fetch_insider(ticker: str, query: str) -> list[dict]:
    """Async wrapper for insider retrieval."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, retrieve_insider, ticker, query)


async def _fetch_price(ticker: str) -> dict:
    """Async wrapper for Finnhub live price."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_live_price, ticker)


async def run_parallel_retrieval(ticker: str, query: str) -> dict:
    """
    Execute all 4 retrieval tasks concurrently and return
    a unified context dict for the synthesis engine.

    Args:
        ticker : Stock ticker e.g. "GME"
        query  : Natural language question from the user

    Returns:
        Unified context dict with results from all 4 layers
    """
    print(f"\n[Workflow] Starting parallel retrieval for {ticker}...")

    # Fan-out: fire all 4 tasks simultaneously
    news_task    = _fetch_news(ticker, query)
    social_task  = _fetch_social(ticker, query)
    insider_task = _fetch_insider(ticker, query)
    price_task   = _fetch_price(ticker)

    # Fan-in: wait for ALL 4 to complete
    news, social, insider, price = await asyncio.gather(
        news_task,
        social_task,
        insider_task,
        price_task,
    )

    print(f"[Workflow] ✅ Retrieved:")
    print(f"  News     : {len(news)} articles")
    print(f"  Social   : {len(social)} posts")
    print(f"  Insider  : {len(insider)} trades")
    print(f"  Price    : ${price.get('current_price', 'N/A')} "
          f"({'LIVE 🟢' if price.get('is_live') else 'MOCK 🟡'})")

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
    Async entry point for the parallel workflow.
    Called by the FastAPI endpoint with await — no new event loop needed
    since FastAPI/uvicorn already manages one.

    Args:
        ticker : Stock ticker e.g. "GME"
        query  : Natural language question from the user

    Returns:
        Unified context dict with results from all 4 layers
    """
    return await run_parallel_retrieval(ticker, query)


if __name__ == "__main__":
    # Quick test — run with: python -m retrieval.workflow
    import json

    TEST_TICKER = "GME"
    TEST_QUERY  = "Should I buy GME stock right now?"

    print(f"\n{'='*55}")
    print(f"  Parallel Workflow Test")
    print(f"  Ticker : {TEST_TICKER}")
    print(f"  Query  : {TEST_QUERY}")
    print(f"{'='*55}")

    context = asyncio.run(retrieve_all(TEST_TICKER, TEST_QUERY))

    print(f"\n── Full Context Summary ────────────────────────────")
    print(f"  Ticker  : {context['ticker']}")
    print(f"  Query   : {context['query']}")

    print(f"\n  News ({len(context['news'])} results):")
    for r in context["news"]:
        print(f"    [{r['relevance']}] {r['metadata'].get('title', '')}")

    print(f"\n  Social ({len(context['social'])} results):")
    for r in context["social"]:
        print(f"    [{r['relevance']}] {r['document'][:90]}")

    print(f"\n  Insider ({len(context['insider'])} results):")
    for r in context["insider"]:
        m = r["metadata"]
        print(f"    [{r['relevance']}] {m.get('executive_role')} "
              f"{m.get('action')} {m.get('shares_volume'):,} shares")

    print(f"\n  Price:")
    for k, v in context["price"].items():
        print(f"    {k:<16} {v}")

    print()