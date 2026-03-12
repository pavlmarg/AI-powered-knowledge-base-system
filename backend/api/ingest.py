"""
api/ingest.py
-------------
POST /api/ingest — triggers a clean re-ingestion of all data layers.

Layer 3 change:
  get_insider_collection() → get_sec_collection()
  The status endpoint now reports SEC filing chunk counts instead of
  insider trade record counts.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from retrieval.chroma_client import (
    reset_all_collections,
    get_news_collection,
    get_social_collection,
    get_sec_collection,
    get_reddit_buzz_collection,
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

    Note: SEC EDGAR fetching adds ~30-60 seconds compared to the old
    static insider JSON ingestion. This is expected — we're fetching
    real regulatory documents from SEC servers.
    """
    try:
        reset_all_collections()
        counts = run_all_ingestion()

        return IngestResponse(
            status  = "success",
            message = f"Successfully ingested {counts['total']} documents across all layers.",
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
        news_count        = get_news_collection().count()
        social_count      = get_social_collection().count()
        sec_count         = get_sec_collection().count()
        reddit_buzz_count = get_reddit_buzz_collection().count()
        total             = news_count + social_count + sec_count + reddit_buzz_count

        return StatusResponse(
            status="online",
            counts={
                "news"        : news_count,
                "social"      : social_count,
                "sec_filings" : sec_count,
                "reddit_buzz" : reddit_buzz_count,
            },
            total=total,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Could not reach ChromaDB: {str(e)}"
        )