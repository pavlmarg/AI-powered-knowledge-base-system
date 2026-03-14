"""
synthesis/schemas.py
--------------------
Pydantic models that define the guaranteed output structure of the
synthesis engine.

Output structures — two paths:

  Path A: AnalysisOutput  (single-stock deep dive)
  ─────────────────────────────────────────────────
  Part 1: AnalysisNarrative — structured CoT breakdown
  Part 2: KnowledgeGraph — React Flow compatible graph

  Path B: GeneralAnalysisOutput  (cross-portfolio / comparison / general)
  ─────────────────────────────────────────────────────────────────────────
  Used for CROSS_PORTFOLIO, COMPARISON, and GENERAL query types.
  Returns a comparative narrative + multi-company knowledge graph.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


# ── Enums ─────────────────────────────────────────────────────────────────────

class RiskLevel(str, Enum):
    LOW       = "LOW"
    MEDIUM    = "MEDIUM"
    HIGH      = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class SentimentLabel(str, Enum):
    BULLISH  = "BULLISH"
    BEARISH  = "BEARISH"
    MIXED    = "MIXED"
    NEUTRAL  = "NEUTRAL"


class NodeType(str, Enum):
    COMPANY   = "Company"
    PERSON    = "Person"
    SENTIMENT = "Sentiment"
    EVENT     = "Event"
    PRICE     = "Price"
    FILING    = "Filing"


class QueryType(str, Enum):
    SINGLE_STOCK    = "single_stock"
    # NEW: 2+ named tickers → focused comparison (not full portfolio fan-out)
    COMPARISON      = "comparison"
    CROSS_PORTFOLIO = "cross_portfolio"
    GENERAL         = "general"
    OUT_OF_SCOPE    = "out_of_scope"


# ── Knowledge Graph Models ────────────────────────────────────────────────────

class GraphNode(BaseModel):
    id     : str      = Field(..., description="Unique identifier e.g. 'GME', 'CEO_Ryan_Cohen', '10K_Risk'.")
    label  : str      = Field(..., description="Human-readable label displayed on the node in the UI.")
    type   : NodeType = Field(..., description="Node category — drives colour/icon in the frontend.")
    detail : str      = Field(..., description="One sentence describing this entity's relevance e.g. '10-K warns of supply chain risk'.")


class GraphEdge(BaseModel):
    id     : str = Field(..., description="Unique edge id e.g. 'GME_to_CEO'.")
    source : str = Field(..., description="Source node id.")
    target : str = Field(..., description="Target node id.")
    label  : str = Field(..., description="Relationship label e.g. 'DISCLOSES_RISK', 'REPORTS_REVENUE', 'WARNS_OF'.")


class KnowledgeGraph(BaseModel):
    nodes : List[GraphNode] = Field(..., description="List of entity nodes.")
    edges : List[GraphEdge] = Field(..., description="List of relationship edges.")


# ── Risk Score ────────────────────────────────────────────────────────────────

class RiskScore(BaseModel):
    risk_percentage  : int   = Field(..., ge=0, le=100)
    risk_label       : str   = Field(...)
    contradiction_detected: bool = Field(...)
    scoring_rationale: str   = Field(...)


# ── Single-Stock Narrative ────────────────────────────────────────────────────

class AnalysisNarrative(BaseModel):
    summary             : str          = Field(..., description="2-3 sentence executive summary.")
    news_analysis       : str          = Field(..., description="Analysis of recent news signals.")
    social_sentiment    : str          = Field(..., description="Analysis of social/Twitter signals.")
    reddit_buzz_signal  : str          = Field(..., description="Analysis of Reddit momentum signal.")
    sec_filings_analysis: str          = Field(..., description="Analysis of SEC filings (10-K/10-Q/8-K).")
    price_context       : str          = Field(..., description="Analysis of recent price action.")
    contradictions      : str          = Field(..., description="Conflicts across data sources, if any.")
    conclusion          : str          = Field(..., description="2-3 sentence synthesised conclusion.")
    risk_level          : RiskLevel    = Field(..., description="Overall risk classification.")
    sentiment_label     : SentimentLabel = Field(..., description="Overall market sentiment.")
    risk_percentage     : int          = Field(..., ge=0, le=100, description="Overall risk 0-100.")


class AnalysisOutput(BaseModel):
    ticker          : str               = Field(..., description="The stock ticker analysed.")
    narrative       : AnalysisNarrative = Field(..., description="Structured CoT analysis.")
    risk_score      : RiskScore         = Field(..., description="Unified risk score.")
    knowledge_graph : KnowledgeGraph    = Field(..., description="React Flow compatible graph.")


# ── Cross-Portfolio / Comparison / General Models ─────────────────────────────

class TickerInsight(BaseModel):
    ticker          : str            = Field(..., description="Stock ticker e.g. 'GME'.")
    relevance_score : float          = Field(..., description="0-1 relevance to the question.")
    summary         : str            = Field(..., description="1-2 sentence insight for this ticker.")
    sentiment_label : SentimentLabel = Field(..., description="Overall sentiment for this ticker.")
    risk_level      : RiskLevel      = Field(..., description="Risk level for this ticker.")
    risk_percentage : int            = Field(..., ge=0, le=100, description="Risk 0-100 for this ticker.")
    key_signal      : str            = Field(..., description="The single most important signal for this ticker.")


class GeneralAnalysisNarrative(BaseModel):
    answer: str = Field(..., description="Direct answer to the user's question in 2-4 sentences.")
    methodology: str = Field(..., description="1-2 sentences explaining how this answer was derived.")
    ticker_insights: List[TickerInsight] = Field(
        ...,
        description=(
            "Ranked list of the most relevant tickers to this question, most relevant first. "
            "For COMPARISON queries, this MUST include an entry for every ticker in the comparison."
        )
    )
    top_ticker: Optional[str] = Field(
        default=None,
        description="The single most relevant/best ticker if one clearly stands out, else null."
    )
    conclusion: str = Field(..., description="2-3 sentence synthesised conclusion across all analysed data.")
    portfolio_risk_summary: str = Field(
        ...,
        description=(
            "1-2 sentence summary of the overall risk picture across all tickers. "
            "e.g. 'GME (87%) carries the highest risk. NVDA (32%) is the most stable.'"
        )
    )


class GeneralAnalysisOutput(BaseModel):
    """
    The complete output for cross-portfolio, comparison, or general questions.
    """
    query_type      : QueryType                = Field(..., description="Classification of the query type.")
    narrative       : GeneralAnalysisNarrative = Field(..., description="Structured comparative analysis.")
    knowledge_graph : KnowledgeGraph           = Field(..., description="React Flow compatible comparative graph.")