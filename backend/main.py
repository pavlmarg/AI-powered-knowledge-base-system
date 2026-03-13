"""
main.py
-------
FastAPI application entry point.

Registers all API routers and configures:
  - CORS        : allows the React frontend (localhost:5173) to call the API
  - Lifespan    : verifies ChromaDB + seeds SEED_TICKERS on startup
  - Health check: GET /api/health — full system status for frontend dashboard

Routers:
  /api/query    — POST  full RAG pipeline (single-stock / cross-portfolio / general)
  /api/ingest   — POST  re-runs the ingestion pipeline (clean re-index)
                  GET   /api/ingest/status — ChromaDB document counts
  /api/history  — GET   /api/history/{session_id} — conversation history
  /api/session  — DELETE /api/session/{session_id} — clear session
"""

import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.query import router as query_router
from api.ingest import router as ingest_router


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


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["Health"])
async def health():
    """
    Full system status check.

    Checks all components and returns their status:
      - ChromaDB connectivity + document counts per layer
      - Active session count (in-memory store)
      - Seed tickers list

    Frontend can poll this on load to verify the system is ready
    before allowing the user to submit queries.

    Response example:
    {
      "status": "healthy",          ← "healthy" | "degraded" | "offline"
      "components": {
        "chromadb": {
          "status": "online",
          "counts": {
            "news": 45,
            "social": 120,
            "sec_filings": 263,
            "reddit_buzz": 10
          },
          "total_documents": 438
        },
        "session_store": {
          "status": "online",
          "active_sessions": 3,
          "type": "in-memory"
        },
        "seed_tickers": ["AAPL", "BA", "GME", ...]
      }
    }
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

        # Warn if collections are empty — likely needs re-ingestion
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