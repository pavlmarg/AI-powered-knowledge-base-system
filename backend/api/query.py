"""
api/query.py
------------
POST /api/query — the main endpoint of the Financial RAG system.

Changes in this version (multi-ticker + follow-up fix):

  1. Multi-ticker extraction (regex + LLM)
     ──────────────────────────────────────
     All extraction functions now return List[str] instead of Optional[str].
     "Compare GME and NVIDIA" → ["GME", "NVDA"]
     "What is Boeing doing?"  → ["BA"]

  2. COMPARISON query type
     ───────────────────────
     When 2+ specific tickers are detected the query is routed as
     COMPARISON (treated as a focused cross-portfolio run over only
     those tickers, NOT the full SEED_TICKERS fan-out).

  3. Follow-up question handling
     ────────────────────────────
     Session history stores a tickers list per turn.
     Follow-ups inherit the tickers list from the previous turn so
     "which one has more risk?" after "compare GME and NVIDIA"
     correctly runs a 2-ticker comparison, not a single-stock query.

  4. OUT_OF_SCOPE routing preserved
     ──────────────────────────────
     Non-financial questions are caught before any retrieval and
     returned immediately with a polite message.

Request body:
  {
    "question"   : "Compare GME and NVIDIA",
    "tickers"    : null,           ← optional list, auto-resolved
    "session_id" : "uuid-here"     ← optional, omit for new session
  }

Response always includes:
  session_id  — persist this on the frontend for follow-up questions
  turn_number — which turn in the conversation this is
  tickers     — list of tickers involved (empty for general/OOS)
"""

import re
import uuid
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from openai import OpenAI

from core.config import SEED_TICKERS, OPENAI_API_KEY, SYNTHESIS_MODEL
from retrieval.workflow import retrieve_all, run_cross_portfolio_retrieval
from synthesis.synthesizer import synthesize, synthesize_general
from synthesis.schemas import QueryType
from memory.session_store import get_history, append_turn, clear_session, session_count
from api.graph import store_graph

router  = APIRouter()
_client = OpenAI(api_key=OPENAI_API_KEY)


# ── Request / Response Models ─────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Natural language question about any stock or the overall market.",
        example="Compare GME and NVIDIA",
    )
    tickers: Optional[List[str]] = Field(
        default=None,
        description=(
            "Optional explicit ticker list e.g. ['GME', 'NVDA']. "
            "Auto-resolved from the question if omitted. "
            "Single-element list = single-stock deep dive. "
            "Multi-element list = comparison / cross-portfolio."
        ),
        example=["GME", "NVDA"],
    )
    # Keep backward-compat: old clients may still send a single ticker string
    ticker: Optional[str] = Field(
        default=None,
        description="Deprecated — prefer `tickers`. If both are provided, `tickers` wins.",
        example="GME",
    )
    session_id: Optional[str] = Field(
        default=None,
        description=(
            "Session identifier for conversation continuity. "
            "If omitted, a new session is created and returned in the response. "
            "Pass the same session_id across turns to enable follow-up questions."
        ),
        example="550e8400-e29b-41d4-a716-446655440000",
    )


class QueryResponse(BaseModel):
    query_type     : str
    tickers        : List[str]          # all tickers involved (empty for general/OOS)
    ticker         : Optional[str]      # backward-compat: first ticker or None
    narrative      : dict
    knowledge_graph: dict
    price          : Optional[dict]
    retrieved_docs : Optional[dict]
    session_id     : str
    turn_number    : int


# ── Stage 1: Fast Regex Multi-Ticker Extraction ───────────────────────────────

def _extract_tickers_regex(question: str) -> List[str]:
    """
    Fast regex-based multi-ticker extraction — zero API cost.

    Looks for:
      1. Explicit cashtags:  $GME  $NVDA
      2. Uppercase words:    GME  NVDA  (2-5 chars, not stopwords)
      3. Company name map:   GameStop → GME, Nvidia → NVDA …

    Returns a deduplicated list preserving first-seen order.
    """
    found: list[str] = []
    seen:  set[str]  = set()

    def _add(t: str) -> None:
        if t and t not in seen:
            seen.add(t)
            found.append(t)

    # 1. Cashtags — most explicit signal
    for t in re.findall(r"\$([A-Z]{1,5})", question):
        _add(t)

    # 2. Uppercase ticker words
    english_stopwords = {
        "I", "A", "AN", "THE", "IS", "ARE", "WAS", "BE",
        "IN", "ON", "AT", "TO", "DO", "GO", "OR", "AND",
        "FOR", "NOT", "BUT", "ALL", "MY", "WE", "IT",
        "US", "CEO", "CFO", "COO", "IPO", "ETF", "AI",
        "EV", "GDP", "CPI", "FED", "SEC", "NYSE", "NASDAQ",
        "RAG", "LLM", "API", "UI", "UX", "VS", "VS.",
    }
    for word in re.findall(r"\b([A-Z]{2,5})\b", question):
        if word not in english_stopwords:
            _add(word)

    # 3. Company name mapping (case-insensitive)
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
    q_lower = question.lower()
    for name, t in name_map.items():
        if name in q_lower:
            _add(t)

    return found


# ── Stage 2: LLM Multi-Ticker Resolution ─────────────────────────────────────

def _extract_tickers_llm(question: str) -> List[str]:
    """
    LLM fallback for freeform questions where regex found nothing.

    Returns a list of tickers explicitly mentioned/implied.
    Returns [] for general / market questions / OOS questions.
    """
    prompt = f"""You are a financial ticker resolver.

The user asked: "{question}"

Task: Identify ALL specific publicly traded companies explicitly mentioned or 
clearly referred to in this question BY NAME or BY TICKER SYMBOL.

Rules:
- Return a comma-separated list of valid stock tickers (1-5 uppercase letters each).
- Return NONE if the question does NOT mention any specific company.
- Return NONE for general investment questions, market questions, and non-financial questions.
- Return NONE for vague follow-ups like "Is that risky?" or "Tell me more" that 
  contain no company reference (context will be resolved from conversation history).

Examples:
  "Compare GME and Nvidia"          → GME,NVDA
  "What is Boeing's outlook?"       → BA
  "Should I buy Tesla or Apple?"    → TSLA,AAPL
  "How is the market doing?"        → NONE
  "What is insider trading?"        → NONE
  "Tell me a joke"                  → NONE

Return ONLY the comma-separated tickers or NONE. No explanation."""

    try:
        response = _client.chat.completions.create(
            model=SYNTHESIS_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=30,
        )
        result = response.choices[0].message.content.strip().upper()
        print(f"[Router] LLM ticker resolution → {result!r}")

        if result == "NONE" or not result:
            return []

        tickers = [t.strip() for t in result.split(",")]
        valid   = [t for t in tickers if t.isalpha() and 1 <= len(t) <= 5]
        return valid

    except Exception as e:
        print(f"[Router] LLM ticker resolution failed: {e}")
        return []


# ── Query Classifier ──────────────────────────────────────────────────────────

def _classify_query(question: str, tickers: List[str]) -> QueryType:
    """
    Determine the routing path for this query.

    Five possible outcomes:
      SINGLE_STOCK    — exactly one ticker → single-stock deep dive
      COMPARISON      — 2+ specific tickers → focused multi-ticker analysis
      CROSS_PORTFOLIO — comparative question across the full seed portfolio
      GENERAL         — broad financial knowledge question
      OUT_OF_SCOPE    — not a financial question at all
    """
    if len(tickers) == 1:
        return QueryType.SINGLE_STOCK

    if len(tickers) >= 2:
        return QueryType.COMPARISON

    # No tickers found — classify by question intent
    prompt = f"""You are a query classifier for a financial analysis system.

Question: "{question}"

Classify into exactly ONE category:

CROSS_PORTFOLIO — compares or ranks stocks from the existing portfolio without 
  naming specific tickers:
  Examples: "Which stock has the most insider selling?"
            "Which companies are most bullish on Reddit?"
            "Are there stocks where insiders disagree with retail sentiment?"

GENERAL — broad financial knowledge, no specific stock needed:
  Examples: "What is insider trading?"
            "What should I invest in?"
            "Explain what a short squeeze is"

OUT_OF_SCOPE — NOT a financial question at all:
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

    Routing:
      SINGLE_STOCK    → 1 ticker found → deep single-stock analysis
      COMPARISON      → 2+ tickers found → focused multi-ticker synthesis
      CROSS_PORTFOLIO → no tickers, portfolio-level question
      GENERAL         → no tickers, broad financial question
      OUT_OF_SCOPE    → non-financial → immediate polite return
    """
    # ── Session management ────────────────────────────────────────────────────
    session_id  = request.session_id or str(uuid.uuid4())
    history     = get_history(session_id)
    turn_number = len(history) // 2 + 1
    print(f"[Session] ID={session_id[:8]}... | Turn={turn_number} | "
          f"History={len(history) // 2} prior turn(s)")

    # ── Step 1: Resolve tickers ───────────────────────────────────────────────
    # Priority: explicit request field > regex > LLM > history inheritance

    # Normalise the incoming request — support both old `ticker` and new `tickers`
    if request.tickers:
        tickers = [t.upper().strip() for t in request.tickers]
    elif request.ticker:
        tickers = [request.ticker.upper().strip()]
    else:
        tickers = _extract_tickers_regex(request.question)
        print(f"[Router] Regex extraction: {tickers}")

        if not tickers:
            tickers = _extract_tickers_llm(request.question)
            print(f"[Router] LLM extraction: {tickers}")

        # ── Step 1b: History-based ticker resolution ──────────────────────────
        # Only if regex + LLM both found nothing.
        #
        # Inherit tickers from the most recent turn so follow-ups work:
        #   "Is that risky?"          after single-stock BA → ["BA"] ✅
        #   "Which one has more risk?" after comparison GME vs NVDA → ["GME","NVDA"] ✅
        #   "Is that risky?"          after portfolio query → [] (portfolio) ✅
        if not tickers and history:
            last_turn         = history[-1]   # always the assistant turn
            inherited_tickers = last_turn.get("tickers", [])
            # Also support old sessions that stored single `ticker`
            if not inherited_tickers and last_turn.get("ticker"):
                inherited_tickers = [last_turn["ticker"]]
            if inherited_tickers:
                tickers = inherited_tickers
                print(f"[Router] Tickers inherited from history → {tickers}")
            else:
                print("[Router] Last turn had no tickers — routing to portfolio")

    # ── Step 2: Classify ──────────────────────────────────────────────────────
    query_type = _classify_query(request.question, tickers)
    print(f"[Router] Final route → type={query_type.value} tickers={tickers}")

    # Convenience: first ticker (or None) for backward compat fields
    primary_ticker = tickers[0] if tickers else None

    # ── Path 0: Out of scope ──────────────────────────────────────────────────
    if query_type == QueryType.OUT_OF_SCOPE:
        return QueryResponse(
            query_type      = query_type.value,
            tickers         = [],
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

    # ── Path A: Single-stock deep dive ────────────────────────────────────────
    if query_type == QueryType.SINGLE_STOCK:
        ticker = primary_ticker
        try:
            context = await retrieve_all(ticker, request.question)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Retrieval failed: {str(e)}")

        try:
            output = synthesize(context, history=history)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")

        answer_summary = (
            f"{output.narrative.summary} "
            f"Risk: {output.narrative.risk_percentage}%. "
            f"{output.narrative.conclusion}"
        )
        append_turn(session_id, request.question, answer_summary, tickers=[ticker])
        store_graph(
            session_id    = session_id,
            nodes         = [n.model_dump() for n in output.knowledge_graph.nodes],
            edges         = [e.model_dump() for e in output.knowledge_graph.edges],
            title         = f"{ticker} Analysis",
            summary       = output.narrative.summary,
            risk_pct      = output.narrative.risk_percentage,
            risk_label    = output.narrative.risk_level,
            contradiction = output.narrative.contradictions,
        )

        return QueryResponse(
            query_type      = query_type.value,
            tickers         = [ticker],
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

    # ── Path B: Comparison — focused multi-ticker analysis ────────────────────
    if query_type == QueryType.COMPARISON:
        print(f"[Router] Comparison mode — fetching data for: {tickers}")
        try:
            # Re-use run_cross_portfolio_retrieval but scoped to the named tickers
            contexts = await run_cross_portfolio_retrieval(
                request.question,
                tickers_override=tickers,   # ← pass explicit list
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Comparison retrieval failed: {str(e)}")

        try:
            output = synthesize_general(contexts, request.question, history=history)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Comparison synthesis failed: {str(e)}")

        answer_summary = (
            f"{output.narrative.answer} "
            f"{output.narrative.conclusion}"
        )
        append_turn(session_id, request.question, answer_summary, tickers=tickers)
        store_graph(
            session_id    = session_id,
            nodes         = [n.model_dump() for n in output.knowledge_graph.nodes],
            edges         = [e.model_dump() for e in output.knowledge_graph.edges],
            title         = f"Comparison: {' vs '.join(tickers)}",
            summary       = output.narrative.portfolio_risk_summary
                            if hasattr(output.narrative, "portfolio_risk_summary") else "",
            risk_pct      = 0,
            risk_label    = "",
            contradiction = "",
        )

        return QueryResponse(
            query_type      = query_type.value,
            tickers         = tickers,
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

    # ── Path C: Cross-portfolio or General ────────────────────────────────────
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
        append_turn(session_id, request.question, answer_summary, tickers=[])
        store_graph(
            session_id    = session_id,
            nodes         = [n.model_dump() for n in output.knowledge_graph.nodes],
            edges         = [e.model_dump() for e in output.knowledge_graph.edges],
            title         = "Portfolio Analysis",
            summary       = output.narrative.portfolio_risk_summary
                            if hasattr(output.narrative, "portfolio_risk_summary") else "",
            risk_pct      = 0,
            risk_label    = "",
            contradiction = "",
        )

        return QueryResponse(
            query_type      = query_type.value,
            tickers         = [],
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
    clear_session(session_id)
    return {"status": "cleared", "session_id": session_id}


@router.get(
    "/sessions/count",
    summary="Number of active sessions (monitoring)",
    tags=["Session"],
)
async def active_sessions():
    return {"active_sessions": session_count()}