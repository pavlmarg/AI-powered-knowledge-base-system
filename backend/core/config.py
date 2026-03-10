"""
core/config.py
--------------
Central configuration for the Financial RAG Engine.
All environment variables and shared constants are loaded here.
Every other module imports from this file — never from os.environ directly.
"""

import os
from dotenv import load_dotenv

# Load .env file from the project root (one level above /backend)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))


# ── Finnhub ───────────────────────────────────────────────────────────────────
FINNHUB_API_KEY: str = os.getenv("FINNHUB_API_KEY", "")

# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
EMBEDDING_MODEL: str = "text-embedding-3-small"   # 1536-dim, cost-efficient
SYNTHESIS_MODEL: str = "gpt-4.1"                    # Used for CoT + structured output

# ── ChromaDB ──────────────────────────────────────────────────────────────────
CHROMA_HOST: str = os.getenv("CHROMA_HOST", "chromadb")   # Docker service name
CHROMA_PORT: int = int(os.getenv("CHROMA_PORT", "8000"))

# Collection names — one per data layer
COLLECTION_NEWS: str    = "layer_news"
COLLECTION_SOCIAL: str  = "layer_social"
COLLECTION_INSIDER: str = "layer_insider"

# ── Data paths ────────────────────────────────────────────────────────────────
DATA_DIR: str = os.path.join(os.path.dirname(__file__), "..", "..", "data")
NEWS_FILE: str    = os.path.join(DATA_DIR, "layer-1-news.json")
SOCIAL_FILE: str  = os.path.join(DATA_DIR, "layer-2-social.json")
INSIDER_FILE: str = os.path.join(DATA_DIR, "layer-3-insider.json")

# ── Known tickers (the 10 companies in scope) ─────────────────────────────────
KNOWN_TICKERS: set = {
    "AAPL", "BA", "GME", "JPM", "NEE",
    "NVDA", "PFE", "PLTR", "TSLA", "XOM"
}

# ── Engagement score weights (Layer 2 normalisation) ─────────────────────────
# Twitter:  likes * 1  +  retweets * 3  +  views * 0.01
# Reddit:   upvotes * 1  +  comments * 2
TWITTER_WEIGHTS: dict = {"likes": 1, "retweets": 3, "views": 0.01}
REDDIT_WEIGHTS: dict  = {"upvotes": 1, "comments": 2}