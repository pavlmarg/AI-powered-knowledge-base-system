"""
api/ingest.py
-------------
POST /api/ingest — triggers a clean re-ingestion of all data layers.

This endpoint allows judges and users to:
  - Re-build the entire vector database from scratch with one API call
  - Verify the ingestion pipeline works without needing terminal access
  - Reset the knowledge base if collections become corrupted

What it does:
  1. Drops all three ChromaDB collections (layer_news, layer_social, layer_insider)
  2. Re-runs the full ingestion pipeline (all 3 layers)
  3. Returns a summary of how many documents were ingested per layer

Security note:
  In a production system this endpoint would be protected by an API key
  or admin role. For the hackathon it is left open for ease of judging.

GET /api/ingest/status — returns the current document counts per collection
  without triggering re-ingestion. Useful for verifying the DB is populated.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from retrieval.chroma_client import (
    reset_all_collections,
    get_news_collection,
    get_social_collection,
    get_insider_collection,
)
from ingestion.run_ingestion import run_all_ingestion

router = APIRouter()


# ── Response Models ───────────────────────────────────────────────────────────

class IngestResponse(BaseModel):
    status  : str
    message : str
    counts  : dict


class StatusResponse(BaseModel):
    status  : str
    counts  : dict
    total   : int


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post(
    "/ingest",
    response_model=IngestResponse,
    summary="Re-ingest all data layers into ChromaDB",
    tags=["Ingestion"],
)
async def ingest():
    """
    Drop all collections and re-run the full ingestion pipeline.

    This will:
      1. Delete all existing vectors from ChromaDB
      2. Re-embed and re-index all 226 documents across 3 layers
      3. Return document counts per layer on completion

    Note: This operation takes 15-30 seconds due to OpenAI embedding calls.
    """
    try:
        # Step 1: Reset all collections
        reset_all_collections()

        # Step 2: Re-run full ingestion pipeline
        counts = run_all_ingestion()

        return IngestResponse(
            status  = "success",
            message = f"Successfully ingested {counts['total']} documents across 3 layers.",
            counts  = counts,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ingestion failed: {str(e)}"
        )


@router.get(
    "/ingest/status",
    response_model=StatusResponse,
    summary="Check current document counts in ChromaDB",
    tags=["Ingestion"],
)
async def ingest_status():
    """
    Return the current number of documents stored per collection.
    Does NOT trigger re-ingestion — read-only status check.
    """
    try:
        news_count    = get_news_collection().count()
        social_count  = get_social_collection().count()
        insider_count = get_insider_collection().count()
        total         = news_count + social_count + insider_count

        return StatusResponse(
            status="online",
            counts={
                "news"   : news_count,
                "social" : social_count,
                "insider": insider_count,
            },
            total=total,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Could not reach ChromaDB: {str(e)}"
        )