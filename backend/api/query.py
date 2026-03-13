"""
api/query.py
------------
POST /api/query — the main endpoint of the Financial RAG system.

Changes in this version:

  1. Conversation memory (session-based)
     ─────────────────────────────────────
     Each request carries an optional session_id. The system loads
     the conversation history for that session and prepends it to the
     synthesis prompt, enabling follow-up questions like:
       "You mentioned Boeing's 10-K warned of supply issues — is that new?"
     History is stored in-memory (memory/session_store.py), last 10 turns,
     TTL 1 hour. Zero extra dependencies.

  2. OUT_OF_SCOPE routing
     ──────────────────────
     Non-financial questions ("Is life beautiful?") are caught by the
     classifier and returned immediately with a polite message —
     no retrieval or synthesis is triggered.

  3. Dynamic ticker support
     ────────────────────────
     Any valid stock ticker is accepted. The system auto-ingests on
     first query via LLM-based ticker resolution (3-stage pipeline).

  4. Query routing — four paths
     ────────────────────────────
     SINGLE_STOCK    → single-stock deep dive (any ticker)
     CROSS_PORTFOLIO → fan-out across SEED_TICKERS
     GENERAL         → fan-out across SEED_TICKERS with broader framing
     OUT_OF_SCOPE    → immediate return, no retrieval

Request body:
  {
    "question"   : "What is Boeing's outlook?",
    "ticker"     : null,           ← optional, auto-resolved
    "session_id" : "uuid-here"     ← optional, omit for new session
  }

Response always includes:
  session_id  — persist this on the frontend for follow-up questions
  turn_number — which turn in the conversation this is
"""

import re
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from openai import OpenAI

from core.config import SEED_TICKERS, OPENAI_API_KEY, SYNTHESIS_MODEL
from retrieval.workflow import retrieve_all, run_cross_portfolio_retrieval
from synthesis.synthesizer import synthesize, synthesize_general
from synthesis.schemas import QueryType
from memory.session_store import get_history, append_turn, clear_session, session_count

router  = APIRouter()
_client = OpenAI(api_key=OPENAI_API_KEY)


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
    session_id: Optional[str] = Field(
        default=None,
        description=(
            "Session identifier for conversation continuity. "
            "If omitted, a new session is created and returned in the response. "
            "Pass the same session_id across turns to enable follow-up questions."
        ),
        example="550e8400-e29b-41d4-a716-446655440000"
    )


class QueryResponse(BaseModel):
    query_type     : str
    ticker         : Optional[str]
    narrative      : dict
    knowledge_graph: dict
    price          : Optional[dict]
    retrieved_docs : Optional[dict]
    session_id     : str   # Always returned — frontend should persist this
    turn_number    : int   # Which turn in the conversation this is


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
    english_stopwords = {
        "I", "A", "AN", "THE", "IS", "ARE", "WAS", "BE",
        "IN", "ON", "AT", "TO", "DO", "GO", "OR", "AND",
        "FOR", "NOT", "BUT", "ALL", "MY", "WE", "IT",
        "US", "CEO", "CFO", "COO", "IPO", "ETF", "AI",
        "EV", "GDP", "CPI", "FED", "SEC", "NYSE", "NASDAQ",
        "RAG", "LLM", "API", "UI", "UX",
    }
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
- If no (comparative, ranking, general, or non-financial question): return NONE

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

    Four possible outcomes:
      SINGLE_STOCK    — question is about a specific ticker
      CROSS_PORTFOLIO — comparative question across multiple stocks
      GENERAL         — broad financial knowledge question
      OUT_OF_SCOPE    — not a financial question at all
    """
    if ticker:
        return QueryType.SINGLE_STOCK

    prompt = f"""You are a query classifier for a financial analysis system.

Question: "{question}"

Classify into exactly ONE category:

CROSS_PORTFOLIO — compares or ranks specific stocks
  Examples: "Which stock has the most insider selling?"
            "Which companies are most bullish on Reddit?"
            "Are there stocks where insiders disagree with retail sentiment?"

GENERAL — broad financial knowledge, no specific stock needed
  Examples: "What is insider trading?"
            "What should I invest in?"
            "Explain what a short squeeze is"

OUT_OF_SCOPE — NOT a financial question at all
  Examples: "Is life beautiful?"
            "What's the weather today?"
            "Tell me a joke"
            "Who won the football match?"
            "Hello, how are you?"

Return ONLY one word: CROSS_PORTFOLIO, GENERAL, or OUT_OF_SCOPE"""

    try:
        response = _client.chat.completions.create(
            model=SYNTHESIS_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=20,
        )
        result = response.choices[0].message.content.strip().upper()
        print(f"[Router] Query classified as: {result}")

        if "OUT_OF_SCOPE" in result:
            return QueryType.OUT_OF_SCOPE
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
    Full Financial RAG pipeline with conversation memory.

    Session flow:
      - First call  : omit session_id → system creates one → returned in response
      - Follow-up   : pass session_id → system loads history → prepends to synthesis
      - New chat    : omit session_id again → fresh session created
    """
    # ── Session management ────────────────────────────────────────────────────
    session_id  = request.session_id or str(uuid.uuid4())
    history     = get_history(session_id)
    turn_number = len(history) // 2 + 1
    print(f"[Session] ID={session_id[:8]}... | Turn={turn_number} | "
          f"History={len(history) // 2} prior turn(s)")

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

    # ── Path 0: Out of scope — return immediately, no retrieval ──────────────
    if query_type == QueryType.OUT_OF_SCOPE:
        return QueryResponse(
            query_type      = query_type.value,
            ticker          = None,
            narrative       = {
                "message": (
                    "This doesn't appear to be a financial question. "
                    "I'm specialised in stock market analysis — try asking about "
                    "a specific company, market trends, or investment topics."
                )
            },
            knowledge_graph = {"nodes": [], "edges": []},
            price           = None,
            retrieved_docs  = None,
            session_id      = session_id,
            turn_number     = turn_number,
        )

    # ── Path A: Single-stock (any ticker, auto-ingests if new) ────────────────
    if query_type == QueryType.SINGLE_STOCK:
        try:
            context = await retrieve_all(ticker, request.question)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Retrieval failed: {str(e)}")

        try:
            output = synthesize(context, history=history)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")

        # Compact summary stored in session — enough context for follow-ups
        answer_summary = (
            f"{output.narrative.summary} "
            f"Risk: {output.narrative.risk_percentage}%. "
            f"{output.narrative.conclusion}"
        )
        append_turn(session_id, request.question, answer_summary, ticker)

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
            session_id      = session_id,
            turn_number     = turn_number,
        )

    # ── Path B: Cross-portfolio or General ────────────────────────────────────
    else:
        try:
            contexts = await run_cross_portfolio_retrieval(request.question)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Portfolio retrieval failed: {str(e)}")

        try:
            output = synthesize_general(contexts, request.question, history=history)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"General synthesis failed: {str(e)}")

        answer_summary = (
            f"{output.narrative.answer} "
            f"{output.narrative.conclusion}"
        )
        append_turn(session_id, request.question, answer_summary, ticker=None)

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
            session_id      = session_id,
            turn_number     = turn_number,
        )


# ── Session management endpoints ──────────────────────────────────────────────

@router.get(
    "/history/{session_id}",
    summary="Get conversation history for a session",
    tags=["Session"],
)
async def get_session_history(session_id: str):
    """
    Return the full conversation history for a given session.

    Useful for:
      - Debugging memory behaviour during frontend development
      - Verifying that history is being stored correctly after each turn
      - The frontend can call this on page load to restore a previous session

    Response format:
      {
        "session_id": "abc-123",
        "turn_count": 3,
        "turns": [
          {"role": "user",      "content": "...", "ticker": "TSLA", "turn": 1},
          {"role": "assistant", "content": "...", "ticker": "TSLA", "turn": 1},
          ...
        ]
      }
    """
    history = get_history(session_id)
    return {
        "session_id" : session_id,
        "turn_count" : len(history) // 2,
        "turns"      : history,
    }


@router.delete(
    "/session/{session_id}",
    summary="Clear conversation history for a session",
    tags=["Session"],
)
async def clear_session_endpoint(session_id: str):
    """
    Clear the conversation history for a given session.
    Call this when the user clicks 'New Chat' on the frontend.
    """
    clear_session(session_id)
    return {"status": "cleared", "session_id": session_id}


@router.get(
    "/sessions/count",
    summary="Number of active sessions (monitoring)",
    tags=["Session"],
)
async def active_sessions():
    """Returns the count of currently active sessions. For monitoring only."""
    return {"active_sessions": session_count()}