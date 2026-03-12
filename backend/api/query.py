"""
api/query.py
------------
POST /api/query — the main endpoint of the Financial RAG system.

Upgrades in this version:

  1. Dynamic ticker support
     ────────────────────────
     The old KNOWN_TICKERS whitelist is gone. Any valid stock ticker
     is now accepted. The system auto-ingests news on first query.

  2. LLM-based ticker resolution (3-stage pipeline)
     ─────────────────────────────────────────────────
     Stage 1: Fast regex  (cashtag / uppercase / company name)  ~0ms
     Stage 2: LLM call to gpt-4.1 for freeform NL resolution   ~400ms
     Stage 3: No ticker → route to cross-portfolio analysis

  3. Query routing
     ──────────────
     SINGLE_STOCK    → single-stock deep dive (any ticker)
     CROSS_PORTFOLIO → fan-out across SEED_TICKERS
     GENERAL         → fan-out across SEED_TICKERS with broader framing

  4. Startup seeding
     ─────────────────
     FastAPI lifespan hook calls seed_on_startup() so SEED_TICKERS
     always have fresh data before the first request arrives.

Request body:
  {
    "question" : "What is Microsoft doing in AI?",
    "ticker"   : null    ← fully optional, auto-resolved
  }
"""

import re
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field
from openai import OpenAI

from core.config import SEED_TICKERS, OPENAI_API_KEY, SYNTHESIS_MODEL
from retrieval.workflow import retrieve_all, run_cross_portfolio_retrieval, seed_on_startup
from synthesis.synthesizer import synthesize, synthesize_general
from synthesis.schemas import QueryType

router = APIRouter()
_client = OpenAI(api_key=OPENAI_API_KEY)


# ── Startup event ─────────────────────────────────────────────────────────────

# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     """
#     FastAPI lifespan hook — runs seed_on_startup() before first request.
#     Register this in main.py:  app = FastAPI(lifespan=lifespan)
#     """
#     await seed_on_startup()
#     yield
#     # (shutdown logic here if needed)


# ── Request / Response Models ─────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Natural language question about any stock or the overall market.",
        example="What is Microsoft doing in the AI space right now?"
    )
    ticker: Optional[str] = Field(
        default=None,
        description="Optional ticker e.g. 'MSFT'. Auto-resolved from question if omitted.",
        example="MSFT"
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
    Fast regex-based ticker extraction — zero API cost.

    Looks for:
      1. Explicit cashtag:  $GME
      2. Uppercase word:    GME  (2-5 chars)
      3. Company name:      GameStop, Tesla, Apple...
    """
    # 1. Cashtag
    cashtags = re.findall(r"\$([A-Z]{1,5})", question)
    if cashtags:
        return cashtags[0]

    # 2. Uppercase ticker word
    words = re.findall(r"\b([A-Z]{2,5})\b", question)
    english_stopwords = {"I", "A", "AN", "THE", "IS", "ARE", "WAS", "BE",
                         "IN", "ON", "AT", "TO", "DO", "GO", "OR", "AND",
                         "FOR", "NOT", "BUT", "ALL", "MY", "WE", "IT",
                         "US", "CEO", "CFO", "COO", "IPO", "ETF", "AI",
                         "EV", "GDP", "CPI", "FED", "SEC", "NYSE", "NASDAQ"}
    for word in words:
        if word not in english_stopwords:
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
        "microsoft"      : "MSFT",
        "amazon"         : "AMZN",
        "google"         : "GOOGL",
        "alphabet"       : "GOOGL",
        "meta"           : "META",
        "netflix"        : "NFLX",
        "intel"          : "INTC",
        "amd"            : "AMD",
        "salesforce"     : "CRM",
        "uber"           : "UBER",
        "airbnb"         : "ABNB",
    }
    question_lower = question.lower()
    for name, ticker in name_map.items():
        if name in question_lower:
            return ticker

    return None


# ── Stage 2: LLM Ticker Resolution ───────────────────────────────────────────

def _extract_ticker_llm(question: str) -> Optional[str]:
    """
    LLM fallback for freeform questions where regex found nothing.
    Uses gpt-4.1 to identify if the question is about one specific
    publicly traded company and returns its ticker.
    """
    prompt = f"""You are a financial ticker resolver.

The user asked: "{question}"

Task: Is this question about ONE specific publicly traded company?
- If yes: return ONLY its stock ticker symbol. Example: MSFT
- If no (comparative, ranking, or general question): return NONE

Rules:
- Return only a valid stock ticker (1-5 uppercase letters) or the word NONE
- No explanation, punctuation, or other text"""

    try:
        response = _client.chat.completions.create(
            model=SYNTHESIS_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=10,
        )
        result = response.choices[0].message.content.strip().upper()
        print(f"[Router] LLM ticker resolution → {result}")

        if result == "NONE" or not result or len(result) > 5:
            return None
        if not result.isalpha():
            return None
        return result

    except Exception as e:
        print(f"[Router] LLM ticker resolution failed: {e}")
        return None


# ── Query Classifier ──────────────────────────────────────────────────────────

def _classify_query(question: str, ticker: Optional[str]) -> QueryType:
    """
    Determine the routing path for this query.

    If a ticker was resolved → always SINGLE_STOCK.
    Otherwise use LLM to classify as CROSS_PORTFOLIO or GENERAL.
    """
    if ticker:
        return QueryType.SINGLE_STOCK

    prompt = f"""Classify this financial question:

Question: "{question}"

CROSS_PORTFOLIO — needs to compare or rank specific stocks
  Examples: "Which stock has the most insider selling?",
            "Which companies are most bullish on Reddit?",
            "Are there stocks where insiders disagree with retail sentiment?"

GENERAL — broad financial knowledge question, no specific stock comparison needed
  Examples: "What is insider trading?",
            "What should I invest in?",
            "Explain what a short squeeze is"

Return ONLY: CROSS_PORTFOLIO or GENERAL"""

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
        print(f"[Router] Classification failed, defaulting to CROSS_PORTFOLIO: {e}")
        return QueryType.CROSS_PORTFOLIO


# ── Route ─────────────────────────────────────────────────────────────────────

@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Analyse any stock or ask a general portfolio question",
    tags=["Query"],
)
async def query(request: QueryRequest):
    """
    Full Financial RAG pipeline — three routing paths:

      SINGLE_STOCK    : Deep dive on any ticker (auto-ingests if new)
      CROSS_PORTFOLIO : Comparative analysis across SEED_TICKERS
      GENERAL         : Broad question answered with portfolio context

    The ticker and path are resolved automatically from the question.
    """
    # ── Step 1: Resolve ticker ────────────────────────────────────────────────
    ticker = request.ticker
    if ticker:
        ticker = ticker.upper().strip()
    else:
        ticker = _extract_ticker_regex(request.question)
        print(f"[Router] Regex extraction: {ticker}")

        if not ticker:
            ticker = _extract_ticker_llm(request.question)
            print(f"[Router] LLM extraction: {ticker}")

    # ── Step 2: Classify ──────────────────────────────────────────────────────
    query_type = _classify_query(request.question, ticker)
    print(f"[Router] Final route → type={query_type.value} ticker={ticker}")

    # ── Step 3 + 4: Retrieve + Synthesize ────────────────────────────────────

    # Path A: Single-stock (any ticker, auto-ingests if new)
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
            query_type      = query_type.value,
            ticker          = ticker,
            narrative       = output.narrative.model_dump(),
            knowledge_graph = {
                "nodes": [n.model_dump() for n in output.knowledge_graph.nodes],
                "edges": [e.model_dump() for e in output.knowledge_graph.edges],
            },
            price           = context["price"],
            retrieved_docs  = {
                "news"        : context["news"],
                "social"      : context["social"],
                "sec_filings" : context["sec_filings"],
                "reddit_buzz" : context.get("reddit_buzz", []),
            },
        )

    # Path B: Cross-portfolio or General
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
            query_type      = query_type.value,
            ticker          = output.narrative.top_ticker,
            narrative       = output.narrative.model_dump(),
            knowledge_graph = {
                "nodes": [n.model_dump() for n in output.knowledge_graph.nodes],
                "edges": [e.model_dump() for e in output.knowledge_graph.edges],
            },
            price           = None,
            retrieved_docs  = None,
        )