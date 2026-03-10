"""
synthesis/synthesizer.py
------------------------
The reasoning engine — takes the unified context from the parallel
retrieval workflow and produces a structured analysis using gpt-4.1
with Chain-of-Thought prompting and OpenAI Structured Outputs.

How it works:
  1. Formats the retrieved context (news, social, insider, price)
     into a clean text block for the LLM prompt
  2. Calls gpt-4.1 with:
       - A system prompt that defines the analyst persona and
         Chain-of-Thought reasoning instructions
       - The formatted context as the user message
       - response_format=AnalysisOutput (Structured Outputs)
  3. Returns a fully validated AnalysisOutput object —
     guaranteed to match the schema, no parsing errors

Why Chain-of-Thought (CoT) prompting:
  A naive prompt like "analyse this stock" produces shallow results.
  CoT forces the model to reason step by step:
    news → social → insider → price → contradictions → conclusion
  Each step builds on the previous, producing deeper insights and
  catching contradictions that a single-pass prompt would miss.

Why Structured Outputs over JSON mode:
  JSON mode guarantees valid JSON syntax but NOT schema adherence —
  the model might omit fields or use wrong key names, crashing React Flow.
  Structured Outputs with Pydantic guarantees 100% schema compliance.
"""

from openai import OpenAI
from core.config import OPENAI_API_KEY, SYNTHESIS_MODEL
from synthesis.schemas import AnalysisOutput

_client = OpenAI(api_key=OPENAI_API_KEY)

# ── Prompt Engineering ────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an elite financial intelligence analyst specialising in 
detecting market signals, insider activity patterns, and contradictions between 
institutional behaviour and retail sentiment.

You will be given a multi-layer intelligence brief about a specific stock containing:
  - Recent news articles
  - Social media sentiment from retail investors
  - Insider trading activity (executives buying or selling)
  - Live market price data

Your task is to reason through each layer systematically and produce a structured 
analysis that identifies the most important signals and contradictions.

REASONING APPROACH — follow this chain of thought strictly:
  Step 1: What do the news articles reveal about the company's fundamentals?
  Step 2: What is the dominant retail sentiment on social media? Is it rational?
  Step 3: What are insiders actually doing? Are they buying or selling?
  Step 4: What does the current price and daily movement signal?
  Step 5: What is the most critical contradiction between these signals?
  Step 6: What is your final synthesized assessment?

IMPORTANT RULES:
  - Be precise and evidence-based — cite specific numbers from the data
  - Insider activity is the strongest signal — weight it heavily
  - When retail sentiment contradicts insider activity, flag this prominently
  - The contradictions field is the most valuable output — be specific
  - Risk levels: LOW=aligned signals, MEDIUM=minor divergence, 
    HIGH=significant contradiction, VERY_HIGH=extreme divergence
  - For the knowledge graph: create nodes for the company, key executives 
    mentioned, sentiment entities, key events, and the current price
  - Every edge source and target MUST exactly match an existing node id
"""


def _format_context(context: dict) -> str:
    """
    Format the unified retrieval context into a structured text prompt.
    This is what gpt-4.1 receives as its intelligence brief.
    """
    ticker = context["ticker"]
    query  = context["query"]
    price  = context["price"]
    lines  = []

    lines.append(f"INTELLIGENCE BRIEF: {ticker}")
    lines.append(f"USER QUERY: {query}")
    lines.append("=" * 60)

    # Price data
    lines.append("\n[LAYER 4 — LIVE MARKET DATA]")
    if "error" not in price:
        lines.append(f"  Current Price  : ${price.get('current_price', 'N/A')}")
        lines.append(f"  Change         : {price.get('change', 'N/A')} "
                     f"({price.get('change_pct', 'N/A')}%)")
        lines.append(f"  Day Range      : ${price.get('day_low', 'N/A')} - "
                     f"${price.get('day_high', 'N/A')}")
        lines.append(f"  Previous Close : ${price.get('previous_close', 'N/A')}")
        data_source = "Real-time" if price.get("is_live") else "Reference data"
        lines.append(f"  Data Source    : {data_source}")
    else:
        lines.append(f"  Price data unavailable: {price.get('error')}")

    # News articles
    lines.append(f"\n[LAYER 1 — NEWS ARTICLES ({len(context['news'])} retrieved)]")
    for i, doc in enumerate(context["news"], 1):
        meta = doc.get("metadata", {})
        lines.append(f"\n  Article {i}: {meta.get('title', 'Untitled')}")
        lines.append(f"  Date    : {meta.get('date_str', 'Unknown')}")
        lines.append(f"  Content : {doc.get('document', '')}")

    # Social media posts
    lines.append(f"\n[LAYER 2 — SOCIAL MEDIA POSTS ({len(context['social'])} retrieved)]")
    for i, doc in enumerate(context["social"], 1):
        meta = doc.get("metadata", {})
        lines.append(f"\n  Post {i} [{meta.get('platform', '')}] "
                     f"by {meta.get('username', '')} "
                     f"(engagement: {meta.get('engagement_score', 0):.0f})")
        lines.append(f"  Content : {doc.get('document', '')}")

    # Insider trading
    lines.append(f"\n[LAYER 3 — INSIDER TRADING ({len(context['insider'])} retrieved)]")
    for i, doc in enumerate(context["insider"], 1):
        meta = doc.get("metadata", {})
        lines.append(f"\n  Trade {i}: {meta.get('executive_role', '')} "
                     f"— {meta.get('action', '')} "
                     f"{meta.get('shares_volume', 0):,} shares")
        lines.append(f"  Date    : {meta.get('date_str', 'Unknown')}")
        lines.append(f"  Detail  : {doc.get('document', '')}")

    return "\n".join(lines)


def synthesize(context: dict) -> AnalysisOutput:
    """
    Run the synthesis engine on a unified retrieval context.

    Uses gpt-4.1 with Structured Outputs to guarantee the response
    exactly matches the AnalysisOutput Pydantic schema.

    Args:
        context: Unified context dict from retrieve_all() containing
                 news, social, insider, and price data

    Returns:
        AnalysisOutput: Fully validated analysis with narrative + knowledge graph
    """
    formatted_context = _format_context(context)

    print(f"\n[Synthesizer] Calling {SYNTHESIS_MODEL}...")

    response = _client.beta.chat.completions.parse(
        model=SYNTHESIS_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": formatted_context},
        ],
        response_format=AnalysisOutput,
        temperature=0.2,  # Low temperature = consistent, precise analysis
    )

    result = response.choices[0].message.parsed

    print(f"[Synthesizer] ✅ Analysis complete.")
    print(f"  Risk Level  : {result.narrative.risk_level.value}")
    print(f"  Sentiment   : {result.narrative.sentiment_label.value}")
    print(f"  Graph Nodes : {len(result.knowledge_graph.nodes)}")
    print(f"  Graph Edges : {len(result.knowledge_graph.edges)}")

    return result


if __name__ == "__main__":
    # Full end-to-end test — run with: python -m synthesis.synthesizer
    # This is the first time the complete RAG pipeline runs:
    # Retrieval → Context → gpt-4.1 → Structured Output
    import json
    from retrieval.workflow import retrieve_all

    TEST_TICKER = "GME"
    TEST_QUERY  = "Should I buy GME stock right now?"

    print(f"\n{'='*60}")
    print(f"  Full RAG Pipeline Test")
    print(f"  Ticker : {TEST_TICKER}")
    print(f"  Query  : {TEST_QUERY}")
    print(f"{'='*60}")

    # Step 1: Retrieve
    context = retrieve_all(TEST_TICKER, TEST_QUERY)

    # Step 2: Synthesize
    output = synthesize(context)

    # Step 3: Display results
    print(f"\n{'='*60}")
    print(f"  ANALYSIS RESULTS")
    print(f"{'='*60}")

    n = output.narrative
    print(f"\n📋 SUMMARY")
    print(f"  {n.summary}")

    print(f"\n📰 NEWS ANALYSIS")
    print(f"  {n.news_analysis}")

    print(f"\n📱 SOCIAL SENTIMENT [{n.sentiment_label.value}]")
    print(f"  {n.social_sentiment}")

    print(f"\n🏦 INSIDER ACTIVITY")
    print(f"  {n.insider_activity}")

    print(f"\n💰 PRICE CONTEXT")
    print(f"  {n.price_context}")

    print(f"\n⚠️  CONTRADICTIONS")
    print(f"  {n.contradictions}")

    print(f"\n🎯 CONCLUSION [Risk: {n.risk_level.value}]")
    print(f"  {n.conclusion}")

    print(f"\n🕸️  KNOWLEDGE GRAPH")
    print(f"  Nodes ({len(output.knowledge_graph.nodes)}):")
    for node in output.knowledge_graph.nodes:
        print(f"    [{node.type.value}] {node.id} — {node.detail}")
    print(f"  Edges ({len(output.knowledge_graph.edges)}):")
    for edge in output.knowledge_graph.edges:
        print(f"    {edge.source} —[{edge.label}]→ {edge.target}")

    print()