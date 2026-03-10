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

Output structure — two parts:

  Part 1: AnalysisNarrative
  ─────────────────────────
  A structured Chain-of-Thought breakdown of the financial situation:
    - summary          : one-line verdict
    - news_analysis    : what the news says
    - social_sentiment : what the crowd thinks (bull/bear/mixed)
    - insider_activity : what insiders are actually doing
    - price_context    : what the live price signals
    - contradictions   : the key conflicts between the above signals
    - conclusion       : final synthesized assessment
    - risk_level       : LOW / MEDIUM / HIGH / VERY_HIGH

  Part 2: KnowledgeGraph
  ──────────────────────
  React Flow compatible graph structure:
    - nodes : entities (Company, Person, Sentiment, Event, Price)
    - edges : relationships between entities

  The frontend renders this directly as an interactive graph.
"""

from pydantic import BaseModel, Field
from typing import List
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


# ── Narrative Analysis Model ──────────────────────────────────────────────────

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


# ── Final Unified Output ──────────────────────────────────────────────────────

class AnalysisOutput(BaseModel):
    """
    The complete output of the synthesis engine.
    Contains both the narrative analysis and the knowledge graph.
    This is what the FastAPI endpoint returns to the frontend.
    """
    ticker          : str              = Field(..., description="The stock ticker analysed.")
    narrative       : AnalysisNarrative = Field(..., description="Structured CoT analysis.")
    knowledge_graph : KnowledgeGraph   = Field(..., description="React Flow compatible graph.")