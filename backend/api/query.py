"""
api/query.py
------------
POST /api/query — the main endpoint of the system.

This is where user input enters the RAG pipeline:
  1. Validates the request (ticker must be one of the 10 known companies)
  2. Extracts the ticker from the question if not provided explicitly
  3. Runs the parallel retrieval workflow (all 4 layers simultaneously)
  4. Passes the unified context to the synthesis engine
  5. Returns the structured analysis + knowledge graph to the frontend

Request body:
  {
    "question" : "Should I buy GME right now?",
    "ticker"   : "GME"          ← optional, auto-extracted if omitted
  }

Response body:
  {
    "ticker"          : "GME",
    "narrative"       : { ...9 analysis fields... },
    "knowledge_graph" : { "nodes": [...], "edges": [...] },
    "price"           : { ...live price data... },
    "retrieved_docs"  : { "news": [...], "social": [...], "insider": [...] }
  }
"""

import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.config import KNOWN_TICKERS
from retrieval.workflow import retrieve_all
from synthesis.synthesizer import synthesize

router = APIRouter()


# ── Request / Response Models ─────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Natural language question about a stock.",
        example="Should I buy GME right now?"
    )
    ticker: str | None = Field(
        default=None,
        description="Stock ticker e.g. 'GME'. Auto-extracted from question if omitted.",
        example="GME"
    )


class QueryResponse(BaseModel):
    ticker         : str
    narrative      : dict
    knowledge_graph: dict
    price          : dict
    retrieved_docs : dict


# ── Ticker extraction ─────────────────────────────────────────────────────────

def _extract_ticker_from_question(question: str) -> str | None:
    """
    Attempt to extract a known ticker from the question text.

    Looks for:
      1. Explicit cashtag:  $GME
      2. Uppercase word:    GME
      3. Company name:      GameStop, Tesla, Apple...
    """
    # 1. Cashtag pattern
    cashtags = re.findall(r"\$([A-Z]{1,5})", question)
    for tag in cashtags:
        if tag in KNOWN_TICKERS:
            return tag

    # 2. Uppercase ticker word
    words = re.findall(r"\b([A-Z]{2,5})\b", question)
    for word in words:
        if word in KNOWN_TICKERS:
            return word

    # 3. Company name mapping
    name_map = {
        "gamestop"  : "GME",
        "tesla"     : "TSLA",
        "nvidia"    : "NVDA",
        "apple"     : "AAPL",
        "palantir"  : "PLTR",
        "jpmorgan"  : "JPM",
        "jp morgan" : "JPM",
        "boeing"    : "BA",
        "pfizer"    : "PFE",
        "nextera"   : "NEE",
        "exxon"     : "XOM",
    }
    question_lower = question.lower()
    for name, ticker in name_map.items():
        if name in question_lower:
            return ticker

    return None


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Analyse a stock using the full RAG pipeline",
    tags=["Query"],
)
async def query(request: QueryRequest):
    """
    Run the full Financial RAG pipeline for a stock query.

    Steps:
      1. Resolve ticker from request or extract from question
      2. Run parallel retrieval across all 4 data layers
      3. Synthesize analysis using gpt-4.1 with CoT prompting
      4. Return structured narrative + knowledge graph + raw docs
    """

    # ── Step 1: Resolve ticker ────────────────────────────────────────────────
    ticker = request.ticker

    if ticker:
        ticker = ticker.upper().strip()
    else:
        ticker = _extract_ticker_from_question(request.question)

    if not ticker:
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not identify a stock ticker from your question. "
                f"Please mention one of: {', '.join(sorted(KNOWN_TICKERS))} "
                "or use a cashtag like $GME."
            )
        )

    if ticker not in KNOWN_TICKERS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Ticker '{ticker}' is not supported. "
                f"Supported tickers: {', '.join(sorted(KNOWN_TICKERS))}"
            )
        )

    # ── Step 2: Parallel retrieval ────────────────────────────────────────────
    try:
        context = await retrieve_all(ticker, request.question)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Retrieval failed: {str(e)}"
        )

    # ── Step 3: Synthesis ─────────────────────────────────────────────────────
    try:
        output = synthesize(context)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Synthesis failed: {str(e)}"
        )

    # ── Step 4: Build response ────────────────────────────────────────────────
    return QueryResponse(
        ticker=ticker,
        narrative=output.narrative.model_dump(),
        knowledge_graph={
            "nodes": [n.model_dump() for n in output.knowledge_graph.nodes],
            "edges": [e.model_dump() for e in output.knowledge_graph.edges],
        },
        price=context["price"],
        retrieved_docs={
            "news"   : context["news"],
            "social" : context["social"],
            "insider": context["insider"],
        },
    )