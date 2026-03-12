"""
synthesis/schemas.py
--------------------
Pydantic models that define the guaranteed output structure of the
synthesis engine.

Layer 3 change:
  AnalysisNarrative.insider_activity → AnalysisNarrative.sec_filings_analysis

  The new field carries a richer analysis: instead of summarising a few
  insider buy/sell transactions, the model now synthesises official SEC
  language from 10-K risk factors, 10-Q quarterly results, and 8-K events.

Output structures — two paths:

  Path A: AnalysisOutput  (single-stock deep dive)
  ─────────────────────────────────────────────────
  Part 1: AnalysisNarrative — structured CoT breakdown:
    - summary, news_analysis, social_sentiment, reddit_buzz_signal,
      sec_filings_analysis, price_context, contradictions, conclusion, risk_level

  Part 2: KnowledgeGraph — React Flow compatible:
    - nodes : entities (Company, Person, Sentiment, Event, Price, Filing)
    - edges : relationships between entities

  Path B: GeneralAnalysisOutput  (cross-portfolio / general questions)
  ──────────────────────────────────────────────────────────────────────
  Used when no specific ticker is identified. Returns:
    - answer         : direct response to the question
    - methodology    : how the answer was derived
    - ticker_insights: per-ticker mini-summaries relevant to the question
    - top_ticker     : the most relevant ticker if one stands out
    - knowledge_graph: a comparative graph across multiple companies
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
    FILING    = "Filing"   # New node type for SEC filings


class QueryType(str, Enum):
    SINGLE_STOCK    = "single_stock"      # e.g. "Should I buy GME?"
    CROSS_PORTFOLIO = "cross_portfolio"   # e.g. "Which stock has the most bearish insiders?"
    GENERAL         = "general"           # e.g. "What is insider trading?"


# ── Knowledge Graph Models ────────────────────────────────────────────────────

class GraphNode(BaseModel):
    """
    A node in the knowledge graph.
    Maps directly to React Flow's node schema.
    """
    id    : str = Field(
        ...,
        description="Unique identifier. Use the entity name e.g. 'GME', 'CEO_Ryan_Cohen', '10K_Risk'."
    )
    label : str = Field(
        ...,
        description="Human-readable label displayed on the node in the UI."
    )
    type  : NodeType = Field(
        ...,
        description="Category of the node: Company, Person, Sentiment, Event, Price, or Filing."
    )
    detail: str = Field(
        ...,
        description="One sentence describing this entity's relevance e.g. '10-K warns of supply chain risk'."
    )


class GraphEdge(BaseModel):
    """
    A directed edge connecting two nodes in the knowledge graph.
    Maps directly to React Flow's edge schema.
    """
    id    : str = Field(
        ...,
        description="Unique identifier for this edge e.g. 'edge_10k_gme'."
    )
    source: str = Field(
        ...,
        description="ID of the origin node. MUST exactly match an existing GraphNode id."
    )
    target: str = Field(
        ...,
        description="ID of the destination node. MUST exactly match an existing GraphNode id."
    )
    label : str = Field(
        ...,
        description="Relationship label on the edge e.g. 'DISCLOSES_RISK', 'REPORTS_REVENUE', 'WARNS_OF'."
    )


class KnowledgeGraph(BaseModel):
    """Complete knowledge graph with nodes and edges."""
    nodes: List[GraphNode] = Field(
        ...,
        description="List of entity nodes. Must include the company, key SEC filing nodes, sentiment, and price."
    )
    edges: List[GraphEdge] = Field(
        ...,
        description="List of directed relationships between nodes."
    )


# ── Narrative Analysis Model (Single-Stock) ───────────────────────────────────

class AnalysisNarrative(BaseModel):
    """
    Structured Chain-of-Thought financial analysis.
    Each field represents one reasoning step.
    """
    summary: str = Field(
        ...,
        description="One sentence verdict on the stock situation e.g. 'TSLA's 10-K warns of margin pressure while Reddit sentiment is strongly bullish — a key contradiction.'"
    )
    news_analysis: str = Field(
        ...,
        description="2-3 sentence analysis of what the news articles reveal about this company."
    )
    social_sentiment: str = Field(
        ...,
        description="2-3 sentence analysis of the social media sentiment from posts. Note dominant emotion and any extreme views. If no posts available, state that."
    )
    reddit_buzz_signal: str = Field(
        ...,
        description=(
            "1-2 sentence analysis of the Reddit buzz data (Layer 5 — ApeWisdom). "
            "State the rank, mention count, upvote count, and trend direction (RISING/FALLING/STABLE/NEW ENTRY). "
            "Interpret what this momentum means e.g. 'MSFT is Rank #9 on Reddit (FALLING from #8), with 64 mentions "
            "and 165 upvotes — modest retail interest, slightly cooling.' "
            "If no Reddit buzz data is available, explicitly state: 'No Reddit buzz data available for this ticker.'"
        )
    )
    sec_filings_analysis: str = Field(
        ...,
        description=(
            "3-4 sentence analysis of what the SEC filings reveal. "
            "Identify the filing type (10-K / 10-Q / 8-K) and date. "
            "Quote or closely paraphrase the most significant risk factor or management statement. "
            "Note any material events from 8-K filings (earnings, M&A, leadership changes). "
            "If no SEC filings are available, state that explicitly."
        )
    )
    price_context: str = Field(
        ...,
        description="1-2 sentence analysis of what the current price and daily movement signals."
    )
    contradictions: str = Field(
        ...,
        description=(
            "The most important conflict between signals — especially between SEC official language "
            "and retail/social sentiment. "
            "e.g. '10-K warns of severe competition and margin compression, yet Reddit is RISING with bullish posts.' "
            "Also consider: SEC risk factors vs news, 8-K material events vs social sentiment. "
            "This is the key insight."
        )
    )
    conclusion: str = Field(
        ...,
        description="2-3 sentence final assessment synthesizing all signals including SEC filings into a coherent view."
    )
    risk_level: RiskLevel = Field(
        ...,
        description="Overall risk assessment: LOW, MEDIUM, HIGH, or VERY_HIGH."
    )


# ── Single-Stock Final Output ─────────────────────────────────────────────────

class AnalysisOutput(BaseModel):
    """
    The complete output of the synthesis engine for a single-stock query.
    Contains both the narrative analysis and the knowledge graph.
    This is what the FastAPI endpoint returns to the frontend.
    """
    ticker          : str               = Field(..., description="The stock ticker analysed.")
    narrative       : AnalysisNarrative = Field(..., description="Structured CoT analysis.")
    knowledge_graph : KnowledgeGraph    = Field(..., description="React Flow compatible graph.")


# ── Cross-Portfolio / General Analysis Models ─────────────────────────────────

class TickerInsight(BaseModel):
    """
    A mini-summary for one ticker within a cross-portfolio response.
    Used when the user asks a comparative or general question.
    """
    ticker          : str            = Field(..., description="Stock ticker e.g. 'GME'.")
    relevance_score : float          = Field(..., description="0-1 score of how relevant this ticker is to the question.")
    summary         : str            = Field(..., description="1-2 sentence insight about this ticker relevant to the question.")
    sentiment_label : SentimentLabel = Field(..., description="Overall sentiment for this ticker combining all available signals.")
    risk_level      : RiskLevel      = Field(..., description="Risk level for this ticker.")
    key_signal      : str            = Field(..., description="The single most important signal for this ticker — can now reference SEC filings e.g. '10-K discloses $2B debt refinancing risk' or 'CEO sold 5M shares'.")


class GeneralAnalysisNarrative(BaseModel):
    """
    Structured response for cross-portfolio or general financial questions.
    """
    answer: str = Field(
        ...,
        description="Direct answer to the user's question in 2-4 sentences."
    )
    methodology: str = Field(
        ...,
        description="1-2 sentences explaining how this answer was derived from the data layers."
    )
    ticker_insights: List[TickerInsight] = Field(
        ...,
        description="Ranked list of the most relevant tickers to this question, most relevant first. Include all tickers with meaningful signal."
    )
    top_ticker: Optional[str] = Field(
        default=None,
        description="The single most relevant ticker if one clearly stands out, else null."
    )
    conclusion: str = Field(
        ...,
        description="2-3 sentence synthesized conclusion across all analysed data."
    )


class GeneralAnalysisOutput(BaseModel):
    """
    The complete output for cross-portfolio or general questions.
    Returns a comparative narrative + a multi-company knowledge graph.
    """
    query_type      : QueryType                = Field(..., description="Classification of the query type.")
    narrative       : GeneralAnalysisNarrative = Field(..., description="Structured comparative analysis.")
    knowledge_graph : KnowledgeGraph           = Field(..., description="React Flow compatible comparative graph.")