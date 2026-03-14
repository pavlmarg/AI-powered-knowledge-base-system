"""
main.py
-------
FastAPI application entry point.

Registers all API routers and configures:
  - CORS        : allows the React frontend (localhost:5173) to call the API
  - Lifespan    : verifies ChromaDB + seeds SEED_TICKERS on startup
  - Health check: GET /api/health — full system status for frontend dashboard
  - Prices      : GET /api/prices — batch live prices for all seed tickers

Routers:
  /api/query    — POST  full RAG pipeline (single-stock / cross-portfolio / general)
  /api/ingest   — POST  re-runs the ingestion pipeline (clean re-index)
                  GET   /api/ingest/status — ChromaDB document counts
  /api/history  — GET   /api/history/{session_id} — conversation history
  /api/session  — DELETE /api/session/{session_id} — clear session
  /api/prices   — GET   batch live prices for all seed tickers (or ?tickers=A,B,C)
"""

import time
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from api.query import router as query_router
from api.ingest import router as ingest_router
from api.graph import router as graph_router


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs once on startup:
      1. Verifies ChromaDB is reachable
      2. Seeds all SEED_TICKERS with fresh data
    Fails fast if ChromaDB is not running.
    """
    from retrieval.chroma_client import get_client
    from retrieval.workflow import seed_on_startup

    startup_start = time.time()

    try:
        client = get_client()
        client.heartbeat()
        print("✅ ChromaDB connection verified.")
    except Exception as e:
        print(f"❌ ChromaDB connection failed: {e}")
        print("   Make sure ChromaDB is running on the configured host/port.")

    await seed_on_startup()

    elapsed = time.time() - startup_start
    print(f"✅ Startup complete in {elapsed:.1f}s — ready to accept requests.")
    yield


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "Financial RAG Engine",
    description = "Multi-layer financial intelligence system with SEC EDGAR, live prices, Reddit buzz, and conversation memory.",
    version     = "2.0.0",
    lifespan    = lifespan,
)


# ── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:3000",   # fallback
        "http://frontend:5173",    # Docker Compose service name
    ],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(query_router,  prefix="/api")
app.include_router(ingest_router, prefix="/api")
app.include_router(graph_router,  prefix="/api")


# ── Batch prices endpoint ──────────────────────────────────────────────────────

@app.get("/api/prices", tags=["Prices"])
async def get_prices(tickers: Optional[str] = Query(default=None)):
    """
    Fetch live prices for multiple tickers in parallel.

    Usage:
      GET /api/prices                    → all SEED_TICKERS
      GET /api/prices?tickers=GME,NVDA   → specific tickers

    Returns:
      {
        "AAPL": { "current_price": 227.50, "change_pct": 0.75, ... },
        "NVDA": { "current_price": 875.40, ... },
        ...
      }

    All 10 seed tickers are fetched in parallel — typical latency ~300ms.
    Falls back to mock data for any ticker where Finnhub fails.
    """
    from retrieval.finnhub_tool import get_live_price
    from core.config import SEED_TICKERS

    # Parse ticker list from query param or use all seeds
    if tickers:
        target = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    else:
        target = sorted(SEED_TICKERS)

    # Fetch all in parallel — asyncio.to_thread wraps the sync Finnhub call
    async def fetch_one(ticker: str) -> tuple[str, dict]:
        data = await asyncio.to_thread(get_live_price, ticker)
        return ticker, data

    results = await asyncio.gather(*[fetch_one(t) for t in target])
    return dict(results)


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["Health"])
async def health():
    """
    Full system status check.

    Checks all components and returns their status:
      - ChromaDB connectivity + document counts per layer
      - Active session count (in-memory store)
      - Seed tickers list
    """
    from retrieval.chroma_client import (
        get_client, get_news_collection, get_social_collection,
        get_sec_collection, get_reddit_buzz_collection,
    )
    from memory.session_store import session_count
    from core.config import SEED_TICKERS

    components = {}
    overall_healthy = True

    # ── ChromaDB ──────────────────────────────────────────────────────────────
    try:
        get_client().heartbeat()
        news_count   = get_news_collection().count()
        social_count = get_social_collection().count()
        sec_count    = get_sec_collection().count()
        reddit_count = get_reddit_buzz_collection().count()
        total        = news_count + social_count + sec_count + reddit_count

        components["chromadb"] = {
            "status": "online",
            "counts": {
                "news"        : news_count,
                "social"      : social_count,
                "sec_filings" : sec_count,
                "reddit_buzz" : reddit_count,
            },
            "total_documents": total,
        }

        if total == 0:
            components["chromadb"]["warning"] = "All collections are empty — run POST /api/ingest"
            overall_healthy = False

    except Exception as e:
        components["chromadb"] = {"status": "offline", "error": str(e)}
        overall_healthy = False

    # ── Session store ─────────────────────────────────────────────────────────
    try:
        components["session_store"] = {
            "status"          : "online",
            "active_sessions" : session_count(),
            "type"            : "in-memory",
            "max_turns"       : 10,
            "ttl_seconds"     : 3600,
        }
    except Exception as e:
        components["session_store"] = {"status": "offline", "error": str(e)}
        overall_healthy = False

    # ── Seed tickers ──────────────────────────────────────────────────────────
    components["seed_tickers"] = sorted(SEED_TICKERS)

    return {
        "status"     : "healthy" if overall_healthy else "degraded",
        "components" : components,
    }


@app.get("/", tags=["Health"])
async def root():
    """Minimal health probe for Docker and load balancers."""
    return {
        "status" : "online",
        "service": "Financial RAG Engine",
        "version": "2.0.0",
        "docs"   : "/docs",
        "health" : "/api/health",
    }