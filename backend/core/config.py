"""
core/config.py
--------------
Central configuration for the Financial RAG Engine.
All environment variables and shared constants are loaded here.
Every other module imports from this file — never from os.environ directly.

Layer 3 architecture change:
  Previously: INSIDER_FILE pointed to a static layer-3-insider.json with
              50 hand-crafted fake insider trade records.

  Now:        Layer 3 is replaced by live SEC EDGAR filings (10-K, 10-Q, 8-K).
              SEC_CIK_MAP maps each seed ticker to its official SEC CIK number.
              The SEC EDGAR API is free and requires no API key.
              TTL is set to 30 days — filings don't change frequently.
"""

import os
from dotenv import load_dotenv

# Load .env file from the project root (one level above /backend)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


# ── Finnhub ───────────────────────────────────────────────────────────────────
FINNHUB_API_KEY: str = os.getenv("FINNHUB_API_KEY", "")

# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY: str  = os.getenv("OPENAI_API_KEY", "")
EMBEDDING_MODEL: str = "text-embedding-3-small"   # 1536-dim, cost-efficient
SYNTHESIS_MODEL: str = "gpt-4.1"                   # Used for CoT + structured output

# ── ChromaDB ──────────────────────────────────────────────────────────────────
CHROMA_HOST: str = os.getenv("CHROMA_HOST", "chromadb")   # Docker service name
CHROMA_PORT: int = int(os.getenv("CHROMA_PORT", "8000"))

# Collection names — one per data layer
COLLECTION_NEWS: str        = "layer_news"
COLLECTION_SOCIAL: str      = "layer_social"
COLLECTION_SEC: str         = "layer_sec"          # Layer 3 — SEC EDGAR filings (replaces layer_insider)
COLLECTION_REDDIT_BUZZ: str = "layer_reddit_buzz"  # Layer 5 — ApeWisdom Reddit buzz

# ── Data paths ────────────────────────────────────────────────────────────────
DATA_DIR: str    = os.path.join(os.path.dirname(__file__), "..", "..", "data")
SOCIAL_FILE: str = os.path.join(DATA_DIR, "layer-2-social.json")
# NOTE: INSIDER_FILE removed — Layer 3 now fetches live from SEC EDGAR.
# NOTE: NEWS_FILE removed   — Layer 1 now fetches live from Finnhub.

# ── Seed tickers — ingested automatically on startup ─────────────────────────
# These are the default watchlist the system always has data for.
# Any ticker outside this list is auto-ingested on first query (on-demand).
SEED_TICKERS: set = {
    "AAPL", "BA", "GME", "JPM", "NEE",
    "NVDA", "PFE", "PLTR", "TSLA", "XOM"
}

# ── SEC EDGAR — Ticker → CIK mapping ─────────────────────────────────────────

SEC_CIK_MAP: dict = {
    "AAPL": "0000320193",
    "BA":   "0000012927",
    "GME":  "0001326380",
    "JPM":  "0000019617",
    "NEE":  "0000753308",
    "NVDA": "0001045810",
    "PFE":  "0000078003",
    "PLTR": "0001321655",
    "TSLA": "0001318605",
    "XOM":  "0000034088",
}

# Filing types to fetch — ordered by information richness
SEC_FILING_TYPES: list = ["10-K", "10-Q", "8-K"]

# How many filings to fetch per type per ticker (keeps context window manageable)
SEC_FILINGS_PER_TYPE: int = 2

# ── Cache TTL ─────────────────────────────────────────────────────────────────
NEWS_CACHE_TTL_DAYS:    int = 3    
REDDIT_BUZZ_CACHE_TTL_DAYS: int = 1   
SEC_CACHE_TTL_DAYS:     int = 30   

# ── Finnhub news fetch window ─────────────────────────────────────────────────
NEWS_FETCH_DAYS: int = int(os.getenv("NEWS_FETCH_DAYS", "30"))

# ── Twitter / Social engagement weights ──────────────────────────────────────
TWITTER_WEIGHTS: dict = {"likes": 1.0, "retweets": 2.0, "views": 0.1}
REDDIT_WEIGHTS:  dict = {"upvotes": 1.0, "comments": 1.5}

APEWISDOM_URL: str = "https://apewisdom.io/api/v1.0/filter/all-stocks"