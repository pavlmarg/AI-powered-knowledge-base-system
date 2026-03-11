"""
api/query.py
------------
POST /api/query — the main endpoint of the Financial RAG system.

This version adds two major upgrades over the original:

  1. LLM-based ticker resolution
     ────────────────────────────
     The original regex-based extractor failed on freeform questions like
     "What do insiders think about the EV company with the most Reddit hype?"
     
     Now there are THREE resolution stages (regex → LLM → cross-portfolio):
       Stage 1: Fast regex (cashtag, uppercase word, company name)  ~0ms
       Stage 2: LLM call to gpt-4.1-mini for fuzzy NL resolution   ~400ms
       Stage 3: No ticker found → route to cross-portfolio analysis

  2. Query routing
     ──────────────
     Questions are classified before retrieval:
       • SINGLE_STOCK    → existing deep-dive pipeline (unchanged)
       • CROSS_PORTFOLIO → fan-out across all 10 tickers, comparative synthesis
       • GENERAL         → cross-portfolio with broader synthesis framing

     The router uses a lightweight LLM call (~200ms) to classify,
     so the overhead is minimal and the routing is reliable.

Request body:
  {
    "question" : "Which stock has the most aggressive insider selling?",
    "ticker"   : null    ← always optional now; LLM resolves if omitted
  }

Response body (single-stock — unchanged):
  {
    "query_type"      : "single_stock",
    "ticker"          : "GME",
    "narrative"       : { ...9 analysis fields... },
    "knowledge_graph" : { "nodes": [...], "edges": [...] },
    "price"           : { ...live price data... },
    "retrieved_docs"  : { "news": [...], "social": [...], "insider": [...] }
  }

Response body (cross-portfolio / general):
  {
    "query_type"      : "cross_portfolio",
    "ticker"          : null,
    "narrative"       : { "answer": ..., "ticker_insights": [...], ... },
    "knowledge_graph" : { "nodes": [...], "edges": [...] },
    "price"           : null,
    "retrieved_docs"  : null
  }
"""

import re
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from openai import OpenAI
from core.config import KNOWN_TICKERS, OPENAI_API_KEY, SYNTHESIS_MODEL
from retrieval.workflow import retrieve_all, run_cross_portfolio_retrieval
from synthesis.synthesizer import synthesize, synthesize_general
from synthesis.schemas import QueryType

router = APIRouter()
_client = OpenAI(api_key=OPENAI_API_KEY)


# ── Request / Response Models ─────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Natural language question. Can reference a specific stock or be a general portfolio question.",
        example="Which stocks have the most bearish insider activity right now?"
    )
    ticker: Optional[str] = Field(
        default=None,
        description="Stock ticker e.g. 'GME'. Fully optional — auto-resolved from question if omitted.",
        example="GME"
    )


class QueryResponse(BaseModel):
    query_type     : str
    ticker         : Optional[str]
    narrative      : dict
    knowledge_graph: dict
    price          : Optional[dict]
    retrieved_docs : Optional[dict]


# ── Stage 1: Fast Regex Ticker Extraction ─────────────────────────────────────

def _extract_ticker_regex(question: str) -> Optional[str]:
    """
    Fast regex-based ticker extraction — runs first, no API cost.

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
        "gamestop"       : "GME",
        "game stop"      : "GME",
        "tesla"          : "TSLA",
        "nvidia"         : "NVDA",
        "apple"          : "AAPL",
        "palantir"       : "PLTR",
        "jpmorgan"       : "JPM",
        "jp morgan"      : "JPM",
        "j.p. morgan"    : "JPM",
        "boeing"         : "BA",
        "pfizer"         : "PFE",
        "nextera"        : "NEE",
        "nextera energy" : "NEE",
        "exxon"          : "XOM",
        "exxonmobil"     : "XOM",
        "exxon mobil"    : "XOM",
    }
    question_lower = question.lower()
    for name, ticker in name_map.items():
        if name in question_lower:
            return ticker

    return None


# ── Stage 2: LLM-Based Ticker Resolution ─────────────────────────────────────

def _extract_ticker_llm(question: str) -> Optional[str]:
    """
    Fallback LLM-based ticker resolver for freeform natural language questions.

    Uses gpt-4.1 to extract a single ticker from questions
    like "What's happening with the EV company Jensen Huang keeps mentioning?"
    
    Returns the ticker string if found, or None if the question is clearly
    a general/comparative question with no single stock intended.
    """
    tickers_list = ", ".join(sorted(KNOWN_TICKERS))

    prompt = f"""You are a financial ticker resolver. 
    
The user has asked: "{question}"

The supported tickers are: {tickers_list}

Task: Determine if this question is about ONE specific company from the list above.
- If yes, return ONLY the ticker symbol. Example: GME
- If the question compares multiple stocks, asks for a ranking, or is a general question about the whole portfolio, return: NONE

Rules:
- Return only the ticker (2-5 uppercase letters) or the word NONE
- No explanation, no punctuation, no other text
- Only return a ticker from the supported list above"""

    try:
        response = _client.chat.completions.create(
            model=SYNTHESIS_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=10,
        )
        result = response.choices[0].message.content.strip().upper()
        print(f"[Router] LLM ticker resolution: '{question[:60]}...' → {result}")

        if result == "NONE" or result not in KNOWN_TICKERS:
            return None
        return result

    except Exception as e:
        print(f"[Router] LLM ticker resolution failed: {e}")
        return None


# ── Query Router ──────────────────────────────────────────────────────────────

def _classify_query(question: str, ticker: Optional[str]) -> QueryType:
    """
    Classify the query type using a lightweight LLM call.

    If a ticker has already been resolved, it's always SINGLE_STOCK.
    Otherwise, classify as CROSS_PORTFOLIO or GENERAL.

    CROSS_PORTFOLIO: requires looking across multiple stocks in our DB
      e.g. "Which stock has the most bearish insiders?"
           "Are there any meme stocks with heavy insider selling?"
    
    GENERAL: can be answered with broad financial knowledge + portfolio data
      e.g. "What is insider trading and why does it matter?"
           "Explain what a bearish signal means"
    """
    if ticker:
        return QueryType.SINGLE_STOCK

    prompt = f"""Classify this financial question into one of two categories:

Question: "{question}"

Categories:
  CROSS_PORTFOLIO — requires comparing or ranking specific stocks in a portfolio
    Examples: "Which stock has the most insider selling?", "Which companies are most bullish on Reddit?", "Are there any stocks where insiders disagree with retail?"
  
  GENERAL — a broad financial question or one that needs general knowledge
    Examples: "What is insider trading?", "Explain what a short squeeze is", "What does bearish mean?"

Return ONLY the category name: CROSS_PORTFOLIO or GENERAL"""

    try:
        response = _client.chat.completions.create(
            model=SYNTHESIS_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=20,
        )
        result = response.choices[0].message.content.strip().upper()
        print(f"[Router] Query classified as: {result}")


        if "GENERAL" in result:
            return QueryType.GENERAL
        return QueryType.CROSS_PORTFOLIO

    except Exception as e:
        print(f"[Router] Query classification failed, defaulting to CROSS_PORTFOLIO: {e}")
        return QueryType.CROSS_PORTFOLIO


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Analyse stocks using the full RAG pipeline",
    tags=["Query"],
)
async def query(request: QueryRequest):
    """
    Run the full Financial RAG pipeline.

    Supports three query modes:
      1. Single-stock:      deep-dive analysis of one company
      2. Cross-portfolio:   comparative analysis across all 10 tickers
      3. General:           broad financial question answered with portfolio context

    The mode is determined automatically — the user never needs to specify it.

    Steps:
      1. Resolve ticker (regex → LLM → none)
      2. Classify query type (single / cross-portfolio / general)
      3. Run appropriate retrieval workflow
      4. Synthesize with appropriate engine
      5. Return unified response
    """

    # ── Step 1: Resolve ticker ────────────────────────────────────────────────
    ticker = request.ticker
    if ticker:
        ticker = ticker.upper().strip()
        if ticker not in KNOWN_TICKERS:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Ticker '{ticker}' is not supported. "
                    f"Supported tickers: {', '.join(sorted(KNOWN_TICKERS))}"
                )
            )
    else:
        # Stage 1: fast regex
        ticker = _extract_ticker_regex(request.question)
        print(f"[Router] Regex extraction: {ticker}")

        # Stage 2: LLM fallback if regex found nothing
        if not ticker:
            ticker = _extract_ticker_llm(request.question)
            print(f"[Router] LLM extraction: {ticker}")

    # ── Step 2: Classify query ────────────────────────────────────────────────
    query_type = _classify_query(request.question, ticker)
    print(f"[Router] Query type: {query_type.value} | Ticker: {ticker}")

    # ── Step 3 & 4: Route to appropriate pipeline ─────────────────────────────

    # ── Path A: Single-stock deep dive ────────────────────────────────────────
    if query_type == QueryType.SINGLE_STOCK:
        try:
            context = await retrieve_all(ticker, request.question)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Retrieval failed: {str(e)}")

        try:
            output = synthesize(context)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")

        return QueryResponse(
            query_type     = query_type.value,
            ticker         = ticker,
            narrative      = output.narrative.model_dump(),
            knowledge_graph= {
                "nodes": [n.model_dump() for n in output.knowledge_graph.nodes],
                "edges": [e.model_dump() for e in output.knowledge_graph.edges],
            },
            price          = context["price"],
            retrieved_docs = {
                "news"   : context["news"],
                "social" : context["social"],
                "insider": context["insider"],
            },
        )

    # ── Path B: Cross-portfolio / General ────────────────────────────────────
    else:
        try:
            contexts = await run_cross_portfolio_retrieval(request.question)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Portfolio retrieval failed: {str(e)}")

        try:
            output = synthesize_general(contexts, request.question)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"General synthesis failed: {str(e)}")

        return QueryResponse(
            query_type     = query_type.value,
            ticker         = output.narrative.top_ticker,
            narrative      = output.narrative.model_dump(),
            knowledge_graph= {
                "nodes": [n.model_dump() for n in output.knowledge_graph.nodes],
                "edges": [e.model_dump() for e in output.knowledge_graph.edges],
            },
            price          = None,
            retrieved_docs = None,
        )