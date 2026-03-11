"""
synthesis/schemas.py
--------------------
Pydantic models that define the guaranteed output structure of the
synthesis engine.

Why this matters:
  Without strict schemas, gpt-4.1 might return JSON with missing keys,
  wrong field names, or inconsistent structure — which would crash the
  frontend's React Flow knowledge graph renderer.

  By using OpenAI's native Structured Outputs (.parse() method) with
  these Pydantic models, we get a 100% guarantee that every response
  conforms exactly to this schema. No validation errors, no crashes.

Output structures — two paths:

  Path A: AnalysisOutput  (single-stock deep dive)
  ─────────────────────────────────────────────────
  Part 1: AnalysisNarrative — structured CoT breakdown:
    - summary, news_analysis, social_sentiment, insider_activity,
      price_context, contradictions, conclusion, risk_level

  Part 2: KnowledgeGraph — React Flow compatible:
    - nodes : entities (Company, Person, Sentiment, Event, Price)
    - edges : relationships between entities

  Path B: GeneralAnalysisOutput  (cross-portfolio / general questions)
  ──────────────────────────────────────────────────────────────────────
  Used when no specific ticker is identified. Returns:
    - answer        : direct response to the question
    - methodology   : how the answer was derived
    - ticker_insights : per-ticker mini-summaries relevant to the question
    - top_ticker    : the most relevant ticker if one stands out
    - knowledge_graph : a comparative graph across multiple companies
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


class QueryType(str, Enum):
    SINGLE_STOCK  = "single_stock"   # e.g. "Should I buy GME?"
    CROSS_PORTFOLIO = "cross_portfolio"  # e.g. "Which stock has the most bearish insiders?"
    GENERAL       = "general"        # e.g. "What is insider trading?"


# ── Knowledge Graph Models ────────────────────────────────────────────────────

class GraphNode(BaseModel):
    """
    A node in the knowledge graph.
    Maps directly to React Flow's node schema.
    """
    id    : str = Field(
        ...,
        description="Unique identifier. Use the entity name e.g. 'GME', 'CEO_Ryan_Cohen'."
    )
    label : str = Field(
        ...,
        description="Human-readable label displayed on the node in the UI."
    )
    type  : NodeType = Field(
        ...,
        description="Category of the node: Company, Person, Sentiment, Event, or Price."
    )
    detail: str = Field(
        ...,
        description="One sentence describing this entity's relevance e.g. 'CEO sold 5.2M shares'."
    )


class GraphEdge(BaseModel):
    """
    A directed edge connecting two nodes in the knowledge graph.
    Maps directly to React Flow's edge schema.
    """
    id    : str = Field(
        ...,
        description="Unique identifier for this edge e.g. 'edge_ceo_gme'."
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
        description="Relationship label on the edge e.g. 'SOLD', 'BULLISH_ON', 'REPORTS'."
    )


class KnowledgeGraph(BaseModel):
    """Complete knowledge graph with nodes and edges."""
    nodes: List[GraphNode] = Field(
        ...,
        description="List of entity nodes. Must include the company, key people, sentiment, and price."
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
        description="One sentence verdict on the stock situation e.g. 'GME shows critical insider-retail divergence with high risk.'"
    )
    news_analysis: str = Field(
        ...,
        description="2-3 sentence analysis of what the news articles reveal about this company."
    )
    social_sentiment: str = Field(
        ...,
        description="2-3 sentence analysis of the social media sentiment. Note dominant emotion and any extreme views."
    )
    sentiment_label: SentimentLabel = Field(
        ...,
        description="Overall social sentiment classification: BULLISH, BEARISH, MIXED, or NEUTRAL."
    )
    insider_activity: str = Field(
        ...,
        description="2-3 sentence analysis of insider trading patterns. Note who is buying or selling and the scale."
    )
    price_context: str = Field(
        ...,
        description="1-2 sentence analysis of what the current price and daily movement signals."
    )
    contradictions: str = Field(
        ...,
        description="The most important conflict between signals e.g. insiders selling while retail is bullish. This is the key insight."
    )
    conclusion: str = Field(
        ...,
        description="2-3 sentence final assessment synthesizing all signals into a coherent view."
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
    ticker          : str           = Field(..., description="Stock ticker e.g. 'GME'.")
    relevance_score : float         = Field(..., description="0-1 score of how relevant this ticker is to the question.")
    summary         : str           = Field(..., description="1-2 sentence insight about this ticker relevant to the question.")
    sentiment_label : SentimentLabel = Field(..., description="Social sentiment for this ticker.")
    risk_level      : RiskLevel     = Field(..., description="Risk level for this ticker.")
    key_signal      : str           = Field(..., description="The single most important signal for this ticker e.g. 'CEO sold 5M shares this week'.")


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
    query_type      : QueryType              = Field(..., description="Classification of the query type.")
    narrative       : GeneralAnalysisNarrative = Field(..., description="Structured comparative analysis.")
    knowledge_graph : KnowledgeGraph          = Field(..., description="React Flow compatible comparative graph.")