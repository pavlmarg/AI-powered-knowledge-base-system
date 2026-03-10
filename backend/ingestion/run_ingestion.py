"""
ingestion/run_ingestion.py
--------------------------
Master script that runs all three ingestion pipelines in sequence.

Usage (from the /backend directory):
    python -m ingestion.run_ingestion

This script is also called internally by the POST /ingest API endpoint,
allowing judges to trigger a clean re-ingestion from the UI without
needing terminal access.
"""

from ingestion.ingest_news import ingest_news
from ingestion.ingest_social import ingest_social
from ingestion.ingest_insider import ingest_insider


def run_all_ingestion() -> dict:
    """
    Execute all three ingestion pipelines sequentially.
    Returns a summary dict with counts per layer.
    """
    print("\n" + "="*55)
    print("  Financial RAG Engine — Data Ingestion Pipeline")
    print("="*55)

    print("\n── Layer 1: News Articles ──────────────────────────")
    news_count = ingest_news()

    print("\n── Layer 2: Social Media Posts ─────────────────────")
    social_count = ingest_social()

    print("\n── Layer 3: Insider Trading Records ────────────────")
    insider_count = ingest_insider()

    total = news_count + social_count + insider_count

    print("\n" + "="*55)
    print(f"  Ingestion complete — {total} total documents")
    print(f"    News     : {news_count}")
    print(f"    Social   : {social_count}")
    print(f"    Insider  : {insider_count}")
    print("="*55 + "\n")

    return {
        "news"    : news_count,
        "social"  : social_count,
        "insider" : insider_count,
        "total"   : total,
    }


if __name__ == "__main__":
    run_all_ingestion()