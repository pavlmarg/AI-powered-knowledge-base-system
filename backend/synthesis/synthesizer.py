"""
synthesis/synthesizer.py
------------------------
The reasoning engine — takes unified context from the parallel retrieval
workflow and produces structured analysis using gpt-4.1 with Chain-of-Thought
prompting and OpenAI Structured Outputs.

Two synthesis paths:

  Path A: synthesize(context)
  ───────────────────────────
  Single-stock deep dive. Takes the unified context dict from retrieve_all()
  and returns a fully validated AnalysisOutput with narrative + knowledge graph.

  Path B: synthesize_general(contexts, query)
  ────────────────────────────────────────────
  Cross-portfolio or general question. Takes a list of context dicts (one per
  ticker) plus the original question and returns a GeneralAnalysisOutput with
  a comparative narrative + multi-company knowledge graph.

Why Structured Outputs over JSON mode:
  JSON mode guarantees valid JSON syntax but NOT schema adherence —
  the model might omit fields or use wrong key names, crashing React Flow.
  Structured Outputs with Pydantic guarantees 100% schema compliance.
"""

from openai import OpenAI
from core.config import OPENAI_API_KEY, SYNTHESIS_MODEL
from synthesis.schemas import AnalysisOutput, GeneralAnalysisOutput

_client = OpenAI(api_key=OPENAI_API_KEY)


# ── Single-Stock Prompt ───────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an elite financial intelligence analyst specialising in 
detecting market signals, insider activity patterns, and contradictions between 
institutional behaviour and retail sentiment.

You will be given a multi-layer intelligence brief about a specific stock containing:
  - Layer 1: Recent news articles (fundamental and institutional signals)
  - Layer 2: Social media posts from retail investors (Twitter/Reddit posts)
  - Layer 3: Insider trading activity (executives buying or selling shares)
  - Layer 4: Live market price data
  - Layer 5: Reddit Buzz data from ApeWisdom — quantitative Reddit activity:
             rank across r/wallstreetbets and finance subreddits, mention count,
             upvote count, and momentum direction (RISING/FALLING/STABLE/NEW ENTRY)

Your task is to reason through each layer systematically and produce a structured 
analysis that identifies the most important signals and contradictions.

REASONING APPROACH — follow this chain of thought strictly:
  Step 1: What do the news articles reveal about the company's fundamentals?
  Step 2: What is the dominant retail sentiment from social media posts?
  Step 3: What does the Reddit Buzz signal reveal about community momentum?
           Use the exact rank, mention count, upvote count, and trend direction.
           A RISING rank with high mentions = growing retail interest.
           A FALLING rank = cooling sentiment even if posts seem positive.
  Step 4: What are insiders actually doing? Are they buying or selling?
  Step 5: What does the current price and daily movement signal?
  Step 6: What is the most critical contradiction between these signals?
           Especially look for: Reddit RISING vs bad news, Reddit FALLING vs
           bullish posts, insiders selling while Reddit momentum is RISING.
  Step 7: What is your final synthesized assessment?

KNOWLEDGE GRAPH INSTRUCTIONS:
  Always create a dedicated Reddit Buzz node when Layer 5 data is present.
  Use it as a Sentiment node with label like "Reddit: Rank #9 FALLING" and
  connect it to the company node and to the overall sentiment node.
  This node should be connected with edges that show whether it reinforces
  or contradicts the news and insider signals."""


# ── General / Cross-Portfolio Prompt ─────────────────────────────────────────

GENERAL_SYSTEM_PROMPT = """You are an elite financial intelligence analyst with access 
to a multi-layer knowledge base covering 10 stocks: AAPL, BA, GME, JPM, NEE, NVDA, 
PFE, PLTR, TSLA, XOM.

You will be given intelligence briefs from multiple stocks and a user question.
Each brief includes news, social posts, insider trades, live price, and Reddit buzz
signals (rank, mentions, upvotes, trend direction from ApeWisdom).

Your job is to answer the question by synthesizing signals across the entire portfolio.

This includes:
  - Comparative questions: "Which stock has the most bearish insiders?"
  - Ranking questions: "Which companies have the highest retail enthusiasm?"
  - Thematic questions: "Are there any stocks where insiders and Reddit disagree?"
  - Reddit-specific: "Which stocks are trending on Reddit right now?"
  - General questions about market trends visible across the portfolio

REASONING APPROACH:
  Step 1: Understand exactly what the user is asking.
  Step 2: For each ticker, extract the signal most relevant to the question.
          Include Reddit buzz rank and trend direction as a primary signal.
  Step 3: Rank or compare tickers based on those signals.
  Step 4: Identify the clearest answer and any interesting cross-ticker patterns.
  Step 5: Synthesize a direct, confident conclusion.

Be specific — use actual numbers from the briefs (share volumes, Reddit ranks,
mention counts, price movements) rather than generic statements."""


# ── Context Formatters ────────────────────────────────────────────────────────

def _format_context(context: dict) -> str:
    """
    Format a single-ticker unified context dict into an LLM-readable
    intelligence brief string. Includes all 5 layers.
    """
    ticker = context["ticker"]
    query  = context["query"]
    price  = context["price"]
    lines  = []

    lines.append(f"INTELLIGENCE BRIEF: {ticker}")
    lines.append(f"USER QUERY: {query}")
    lines.append("=" * 60)

    # ── Layer 4: Price ────────────────────────────────────────────────────────
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

    # ── Layer 1: News ─────────────────────────────────────────────────────────
    lines.append(f"\n[LAYER 1 — NEWS ARTICLES ({len(context['news'])} retrieved)]")
    for i, doc in enumerate(context["news"], 1):
        meta = doc.get("metadata", {})
        lines.append(f"\n  Article {i}: {meta.get('title', 'Untitled')}")
        lines.append(f"  Date    : {meta.get('date_str', 'Unknown')}")
        lines.append(f"  Content : {doc.get('document', '')}")

    # ── Layer 2: Social posts ─────────────────────────────────────────────────
    lines.append(f"\n[LAYER 2 — SOCIAL MEDIA POSTS ({len(context['social'])} retrieved)]")
    if context["social"]:
        for i, doc in enumerate(context["social"], 1):
            meta = doc.get("metadata", {})
            lines.append(f"\n  Post {i} [{meta.get('platform', '')}] "
                         f"by {meta.get('username', '')} "
                         f"(engagement: {meta.get('engagement_score', 0):.0f})")
            lines.append(f"  Content : {doc.get('document', '')}")
    else:
        lines.append("  No social media posts available for this ticker.")

    # ── Layer 3: Insider trading ──────────────────────────────────────────────
    lines.append(f"\n[LAYER 3 — INSIDER TRADING ({len(context['insider'])} retrieved)]")
    if context["insider"]:
        for i, doc in enumerate(context["insider"], 1):
            meta = doc.get("metadata", {})
            lines.append(f"\n  Trade {i}: {meta.get('executive_role', '')} "
                         f"— {meta.get('action', '')} "
                         f"{meta.get('shares_volume', 0):,} shares")
            lines.append(f"  Date    : {meta.get('date_str', 'Unknown')}")
            lines.append(f"  Detail  : {doc.get('document', '')}")
    else:
        lines.append("  No insider trading records available for this ticker.")

    # ── Layer 5: Reddit Buzz ──────────────────────────────────────────────────
    reddit_buzz = context.get("reddit_buzz", [])
    lines.append(f"\n[LAYER 5 — REDDIT BUZZ / APEWISDOM ({len(reddit_buzz)} signal(s) retrieved)]")
    if reddit_buzz:
        for doc in reddit_buzz:
            meta = doc.get("metadata", {})
            lines.append(f"\n  {doc.get('document', '')}")
            lines.append(f"  Raw Stats — Rank: #{meta.get('rank', 'N/A')} "
                         f"(was #{meta.get('rank_24h_ago', 'N/A')} yesterday) | "
                         f"Mentions: {meta.get('mentions', 0):,} | "
                         f"Upvotes: {meta.get('upvotes', 0):,}")
    else:
        lines.append("  No Reddit buzz data available for this ticker "
                     "(ticker not ranked on ApeWisdom — low Reddit activity).")

    return "\n".join(lines)


def _format_multi_context(contexts: list[dict], query: str) -> str:
    """
    Format multiple single-ticker contexts into a combined brief for
    cross-portfolio synthesis. Each ticker gets a compact section
    including Reddit buzz signal.
    """
    lines = []
    lines.append(f"USER QUESTION: {query}")
    lines.append(f"PORTFOLIO INTELLIGENCE BRIEF — {len(contexts)} stocks")
    lines.append("=" * 60)

    for context in contexts:
        ticker = context["ticker"]
        price  = context["price"]

        lines.append(f"\n{'─' * 40}")
        lines.append(f"TICKER: {ticker}")

        # Price
        if "error" not in price:
            lines.append(
                f"  Price: ${price.get('current_price', 'N/A')} "
                f"({price.get('change_pct', 'N/A')}% today)"
            )

        # Top news headline only (keep brief for cross-portfolio)
        if context["news"]:
            top_news = context["news"][0]
            meta = top_news.get("metadata", {})
            lines.append(f"  Top News: {meta.get('title', 'N/A')} [{meta.get('date_str', '')}]")
            lines.append(f"    {top_news.get('document', '')[:200]}...")

        # Social — top post by engagement
        if context["social"]:
            top_social = context["social"][0]
            meta = top_social.get("metadata", {})
            lines.append(
                f"  Top Social [{meta.get('platform', '')}] "
                f"engagement={meta.get('engagement_score', 0):.0f}: "
                f"{top_social.get('document', '')[:150]}..."
            )

        # Insider — all trades (key signal layer)
        if context["insider"]:
            lines.append(f"  Insider Trades ({len(context['insider'])}):")
            for doc in context["insider"]:
                meta = doc.get("metadata", {})
                lines.append(
                    f"    • {meta.get('executive_role', '')} "
                    f"{meta.get('action', '')} "
                    f"{meta.get('shares_volume', 0):,} shares "
                    f"[{meta.get('date_str', '')}]"
                )

        # Reddit Buzz — compact one-liner per ticker
        reddit_buzz = context.get("reddit_buzz", [])
        if reddit_buzz:
            doc  = reddit_buzz[0]
            meta = doc.get("metadata", {})
            rank     = meta.get("rank", "N/A")
            rank_ago = meta.get("rank_24h_ago", "N/A")
            mentions = meta.get("mentions", 0)
            upvotes  = meta.get("upvotes", 0)
            # Derive trend label from ranks
            if isinstance(rank, int) and isinstance(rank_ago, int) and rank_ago > 0:
                if rank < rank_ago:
                    trend = "RISING 📈"
                elif rank > rank_ago:
                    trend = "FALLING 📉"
                else:
                    trend = "STABLE ➡️"
            else:
                trend = "NEW ENTRY"
            lines.append(
                f"  Reddit Buzz: Rank #{rank} {trend} (was #{rank_ago}) | "
                f"{mentions:,} mentions | {upvotes:,} upvotes"
            )
        else:
            lines.append("  Reddit Buzz: Not ranked (low Reddit activity)")

    return "\n".join(lines)


# ── Synthesis Functions ───────────────────────────────────────────────────────

def synthesize(context: dict) -> AnalysisOutput:
    """
    Run the synthesis engine on a single-ticker unified retrieval context.

    Uses gpt-4.1 with Structured Outputs to guarantee the response
    exactly matches the AnalysisOutput Pydantic schema.

    Args:
        context: Unified context dict from retrieve_all() containing
                 news, social, insider, price, and reddit_buzz data.

    Returns:
        AnalysisOutput: Fully validated analysis with narrative + knowledge graph.
    """
    formatted_context = _format_context(context)

    print(f"\n[Synthesizer] Single-stock synthesis for {context['ticker']}...")
    print(f"[Synthesizer] Calling {SYNTHESIS_MODEL}...")

    response = _client.beta.chat.completions.parse(
        model=SYNTHESIS_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": formatted_context},
        ],
        response_format=AnalysisOutput,
        temperature=0.2,
    )

    result = response.choices[0].message.parsed

    print(f"[Synthesizer] ✅ Single-stock analysis complete.")
    print(f"  Risk Level  : {result.narrative.risk_level.value}")
    print(f"  Sentiment   : {result.narrative.sentiment_label.value}")
    print(f"  Graph Nodes : {len(result.knowledge_graph.nodes)}")
    print(f"  Graph Edges : {len(result.knowledge_graph.edges)}")

    return result


def synthesize_general(contexts: list[dict], query: str) -> GeneralAnalysisOutput:
    """
    Run cross-portfolio synthesis for general or comparative questions.

    Takes intelligence briefs from multiple tickers and answers the user's
    question by synthesizing signals across the whole portfolio.

    Args:
        contexts: List of unified context dicts, one per ticker.
        query:    The original user question.

    Returns:
        GeneralAnalysisOutput: Validated comparative analysis + knowledge graph.
    """
    formatted_context = _format_multi_context(contexts, query)

    tickers_covered = [c["ticker"] for c in contexts]
    print(f"\n[Synthesizer] Cross-portfolio synthesis across {tickers_covered}...")
    print(f"[Synthesizer] Calling {SYNTHESIS_MODEL}...")

    response = _client.beta.chat.completions.parse(
        model=SYNTHESIS_MODEL,
        messages=[
            {"role": "system", "content": GENERAL_SYSTEM_PROMPT},
            {"role": "user",   "content": formatted_context},
        ],
        response_format=GeneralAnalysisOutput,
        temperature=0.2,
    )

    result = response.choices[0].message.parsed

    print(f"[Synthesizer] ✅ Cross-portfolio analysis complete.")
    print(f"  Query Type  : {result.query_type.value}")
    print(f"  Top Ticker  : {result.narrative.top_ticker or 'N/A'}")
    print(f"  Insights    : {len(result.narrative.ticker_insights)} tickers")
    print(f"  Graph Nodes : {len(result.knowledge_graph.nodes)}")
    print(f"  Graph Edges : {len(result.knowledge_graph.edges)}")

    return result


# ── Dev / Test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio
    import json
    from retrieval.workflow import retrieve_all, run_cross_portfolio_retrieval

    print("\n" + "=" * 60)
    print("  [TEST A] Single-stock synthesis")
    print("=" * 60)

    TEST_TICKER = "GME"
    TEST_QUERY  = "Should I buy GME stock right now?"

    context = asyncio.run(retrieve_all(TEST_TICKER, TEST_QUERY))
    output  = synthesize(context)

    n = output.narrative
    print(f"\n📋 SUMMARY\n  {n.summary}")
    print(f"\n📱 REDDIT BUZZ\n  {n.reddit_buzz_signal}")
    print(f"\n⚠️  CONTRADICTIONS\n  {n.contradictions}")
    print(f"\n🎯 CONCLUSION [Risk: {n.risk_level.value}]\n  {n.conclusion}")

    print("\n" + "=" * 60)
    print("  [TEST B] Cross-portfolio synthesis")
    print("=" * 60)

    GENERAL_QUERY = "Which stocks are trending on Reddit right now?"
    contexts = asyncio.run(run_cross_portfolio_retrieval(GENERAL_QUERY))
    general_output = synthesize_general(contexts, GENERAL_QUERY)

    g = general_output.narrative
    print(f"\n💬 ANSWER\n  {g.answer}")
    print(f"\n🏆 TOP TICKER\n  {g.top_ticker}")
    print(f"\n🎯 CONCLUSION\n  {g.conclusion}")
    print(f"\n📊 TICKER INSIGHTS:")
    for insight in g.ticker_insights:
        print(f"  [{insight.ticker}] {insight.key_signal} (relevance: {insight.relevance_score:.2f})")