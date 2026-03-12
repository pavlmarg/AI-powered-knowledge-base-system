"""
ingestion/run_ingestion.py
--------------------------
Master script that runs all ingestion pipelines in sequence.

Usage (from the /backend directory):
    python -m ingestion.run_ingestion

Layer 3 change:
  ingest_insider() → ingest_sec()
  Static JSON with 50 fake trades → live SEC EDGAR filings (10-K, 10-Q, 8-K)

Note: SEC ingestion is slower than the old insider ingestion because it
makes real HTTP requests to SEC EDGAR. Expect ~30-60s for 10 tickers.
"""

from ingestion.ingest_news import ingest_news
from ingestion.ingest_social import ingest_social
from ingestion.ingest_sec import ingest_sec
from ingestion.ingest_reddit_buzz import ingest_reddit_buzz


def run_all_ingestion() -> dict:
    """
    Execute all ingestion pipelines sequentially.
    Returns a summary dict with counts per layer.
    """
    print("\n" + "="*55)
    print("  Financial RAG Engine — Data Ingestion Pipeline")
    print("="*55)

    print("\n── Layer 1: News Articles ──────────────────────────")
    news_count = ingest_news()

    print("\n── Layer 2: Social Media Posts ─────────────────────")
    social_count = ingest_social()

    print("\n── Layer 3: SEC EDGAR Filings ───────────────────────")
    sec_count = ingest_sec()

    print("\n── Layer 5: Reddit Buzz (ApeWisdom) ────────────────")
    reddit_buzz_count = ingest_reddit_buzz()

    total = news_count + social_count + sec_count + reddit_buzz_count

    print("\n" + "="*55)
    print(f"  Ingestion complete — {total} total documents/chunks")
    print(f"    News        : {news_count}")
    print(f"    Social      : {social_count}")
    print(f"    SEC Filings : {sec_count}")
    print(f"    Reddit Buzz : {reddit_buzz_count}")
    print("="*55 + "\n")

    return {
        "news"        : news_count,
        "social"      : social_count,
        "sec_filings" : sec_count,
        "reddit_buzz" : reddit_buzz_count,
        "total"       : total,
    }


if __name__ == "__main__":
    run_all_ingestion()