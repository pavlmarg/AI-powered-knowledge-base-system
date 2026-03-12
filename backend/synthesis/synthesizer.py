"""
synthesis/synthesizer.py
------------------------
The reasoning engine — takes unified context from the parallel retrieval
workflow and produces structured analysis using gpt-4.1 with Chain-of-Thought
prompting and OpenAI Structured Outputs.

Layer 3 change:
  - SYSTEM_PROMPT updated: Step 4 now instructs the model to reason over
    SEC filings (risk factors, MD&A, 8-K events) instead of insider trades.
  - _format_context() updated: LAYER 3 section now formats SEC filing chunks
    with their filing type, date, and section name instead of trade records.
  - _format_multi_context() updated: cross-portfolio briefs now include
    the most relevant SEC filing signal per ticker.

The key improvement: the model can now say things like:
  "Tesla's 10-K Risk Factors warn that 'increased competition from legacy
  automakers could materially reduce our market share' — yet retail sentiment
  on Reddit is strongly bullish. This is the critical contradiction."

Rather than only:
  "The CEO sold 500,000 shares."
"""

from openai import OpenAI
from core.config import OPENAI_API_KEY, SYNTHESIS_MODEL
from synthesis.schemas import AnalysisOutput, GeneralAnalysisOutput

_client = OpenAI(api_key=OPENAI_API_KEY)


# ── Single-Stock System Prompt ────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an elite financial intelligence analyst specialising in 
detecting market signals, official company disclosures, and contradictions between 
what companies officially report and what retail investors believe.

You will be given a multi-layer intelligence brief about a specific stock containing:
  - Layer 1: Recent news articles (fundamental and institutional signals)
  - Layer 2: Social media posts from retail investors (Twitter/Reddit posts)
  - Layer 3: SEC EDGAR filings — official documents filed with the US regulator:
             10-K (annual report): risk factors, management discussion & analysis
             10-Q (quarterly report): interim financials, updated risks
             8-K (material event): earnings, M&A announcements, CEO changes
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
  Step 4: What do the SEC filings officially disclose?
           Identify which filing type each chunk comes from (10-K / 10-Q / 8-K).
           For 10-K / 10-Q: what specific risks does management disclose?
           What does the MD&A section say about revenue, margins, and outlook?
           For 8-K: what material event occurred? (earnings beat/miss, M&A, CEO change)
           Quote or closely paraphrase the most significant management statement.
  Step 5: What does the current price and daily movement signal?
  Step 6: What is the most critical contradiction between these signals?
           Priority contradictions to look for:
           - SEC risk factors warn of X while Reddit/social is bullish about X
           - 8-K earnings miss while retail sentiment remains optimistic
           - MD&A shows declining margins while news is positive
           - Management language is cautious/hedged while price is rising
  Step 7: What is your final synthesized assessment?

KNOWLEDGE GRAPH INSTRUCTIONS:
  Always create Filing nodes for SEC documents when Layer 3 data is present.
  Use node type 'Filing' with labels like '10-K: Risk Factors' or '8-K: Earnings'.
  Connect Filing nodes to the Company node with edges like 'DISCLOSES', 'REPORTS', 'WARNS_OF'.
  Connect Filing nodes to Sentiment nodes when the filing contradicts retail sentiment.
  Also create a Reddit Buzz node when Layer 5 data is present."""


# ── General / Cross-Portfolio System Prompt ───────────────────────────────────

GENERAL_SYSTEM_PROMPT = """You are an elite financial intelligence analyst with access 
to a multi-layer knowledge base covering 10 stocks: AAPL, BA, GME, JPM, NEE, NVDA, 
PFE, PLTR, TSLA, XOM.

You will be given intelligence briefs from multiple stocks and a user question.
Each brief includes news, social posts, official SEC filings (10-K/10-Q/8-K),
live price, and Reddit buzz signals (rank, mentions, upvotes, trend direction).

Layer 3 is now SEC EDGAR filings — this means you have access to official 
company language about risks, financial results, and material events. 
Use this to give answers grounded in what companies officially disclosed,
not just what media or social media say.

Your job is to answer the question by synthesizing signals across the entire portfolio.

This includes:
  - Comparative questions: "Which stock has the most risk disclosures?"
  - Ranking questions: "Which companies have the highest retail enthusiasm?"
  - Thematic questions: "Are there stocks where SEC filings contradict Reddit sentiment?"
  - SEC-specific: "Which companies had the most material 8-K events recently?"
  - General questions about market trends visible across the portfolio

REASONING APPROACH:
  Step 1: Understand exactly what the user is asking.
  Step 2: For each ticker, extract the signal most relevant to the question.
          Include SEC filing content AND Reddit buzz as primary signals.
  Step 3: Rank or compare tickers based on those signals.
  Step 4: Identify the clearest answer and any interesting cross-ticker patterns.
  Step 5: Synthesize a direct, confident conclusion.

Be specific — reference actual SEC filing content (risk factor language, 
revenue figures from MD&A, 8-K event details) alongside Reddit ranks and 
mention counts rather than generic statements."""


# ── Context Formatters ────────────────────────────────────────────────────────

def _format_context(context: dict) -> str:
    """
    Format a single-ticker unified context dict into an LLM-readable
    intelligence brief string. Includes all 5 layers.

    Layer 3 now formats SEC filing chunks instead of insider trade records.
    Each chunk includes its filing type, date, and section for clear attribution.
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

    # ── Layer 3: SEC Filings ──────────────────────────────────────────────────
    sec_filings = context.get("sec_filings", [])
    lines.append(f"\n[LAYER 3 — SEC EDGAR FILINGS ({len(sec_filings)} chunks retrieved)]")
    if sec_filings:
        for i, doc in enumerate(sec_filings, 1):
            meta = doc.get("metadata", {})
            filing_type = meta.get("filing_type", "Unknown")
            filed_date  = meta.get("filed_date", "Unknown")
            section     = meta.get("section", "Unknown")
            acc_no      = meta.get("accession_no", "")

            lines.append(f"\n  Filing {i}: {filing_type} — {section}")
            lines.append(f"  Filed   : {filed_date}  (Accession: {acc_no})")
            lines.append(f"  Content : {doc.get('document', '')}")
            lines.append(f"  Relevance: {doc.get('relevance', 0):.3f}")
    else:
        lines.append("  No SEC filings available for this ticker.")

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
    including the most relevant SEC filing signal.
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
            lines.append(f"  Top Social [{meta.get('platform', '')}]: "
                         f"{top_social.get('document', '')[:150]}...")

        # SEC Filings — most relevant chunk (top-1 by semantic relevance)
        sec_filings = context.get("sec_filings", [])
        if sec_filings:
            top_sec  = sec_filings[0]
            meta     = top_sec.get("metadata", {})
            lines.append(f"  SEC Filing ({meta.get('filing_type', '?')} "
                         f"{meta.get('filed_date', '?')} — {meta.get('section', '?')}):")
            lines.append(f"    {top_sec.get('document', '')[:300]}...")
        else:
            lines.append("  SEC Filings: None available")

        # Reddit buzz
        reddit_buzz = context.get("reddit_buzz", [])
        if reddit_buzz:
            meta = reddit_buzz[0].get("metadata", {})
            rank      = meta.get("rank", "N/A")
            rank_prev = meta.get("rank_24h_ago", "N/A")
            mentions  = meta.get("mentions", 0)
            upvotes   = meta.get("upvotes", 0)
            trend     = "RISING" if (rank != "N/A" and rank_prev != "N/A" and rank < rank_prev) else \
                        "FALLING" if (rank != "N/A" and rank_prev != "N/A" and rank > rank_prev) else "STABLE"
            lines.append(f"  Reddit: Rank #{rank} (was #{rank_prev}) — "
                         f"{mentions:,} mentions, {upvotes:,} upvotes [{trend}]")
        else:
            lines.append("  Reddit: Not ranked on ApeWisdom")

    return "\n".join(lines)


# ── Synthesis functions ───────────────────────────────────────────────────────

def synthesize(context: dict) -> AnalysisOutput:
    """
    Run single-stock synthesis with Chain-of-Thought reasoning.

    Uses gpt-4.1 with Structured Outputs to guarantee the response
    exactly matches the AnalysisOutput Pydantic schema.
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
    print(f"  Graph Nodes : {len(result.knowledge_graph.nodes)}")
    print(f"  Graph Edges : {len(result.knowledge_graph.edges)}")

    return result


def synthesize_general(contexts: list[dict], query: str) -> GeneralAnalysisOutput:
    """
    Run cross-portfolio synthesis for general or comparative questions.
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
    return result