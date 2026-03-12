"""
main.py
-------
FastAPI application entry point.

Registers all API routers and configures:
  - CORS: allows the React frontend (localhost:5173) to call the API
  - Lifespan: confirms ChromaDB connection on startup
  - Health check: GET / for Docker and load balancer health probes

Routers:
  /api/query   — POST  triggers the full RAG pipeline for a ticker + question
  /api/ingest  — POST  re-runs the ingestion pipeline (clean re-index)
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.query import router as query_router
from api.ingest import router as ingest_router
from retrieval.workflow import seed_on_startup
# from api.query import lifespan

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs once on startup — verifies ChromaDB is reachable before
    accepting traffic. Fails fast if the DB is not running.
    """
    from retrieval.chroma_client import get_client
    try:
        client = get_client()
        client.heartbeat()
        print("✅ ChromaDB connection verified.")
    except Exception as e:
        print(f"❌ ChromaDB connection failed: {e}")
        print("   Make sure ChromaDB is running on the configured host/port.")

    await seed_on_startup()
    yield


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Financial RAG Engine", lifespan=lifespan)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Allows the React frontend (Vite default port 5173) to call the API.
# In production (Docker), the frontend container is added here too.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:3000",   # fallback
        "http://frontend:5173",    # Docker Compose service name
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(query_router,  prefix="/api")
app.include_router(ingest_router, prefix="/api")


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint for Docker and load balancers."""
    return {
        "status" : "online",
        "service": "Financial RAG Reasoning Engine",
        "version": "1.0.0",
    }